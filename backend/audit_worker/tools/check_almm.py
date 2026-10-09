"""
backend/audit_worker/tools/check_almm.py
-----------------------------------------
Checks if a solar panel brand/model is on MNRE's ALMM List-I (DCR certified).
Uses multi-strategy matching: exact → prefix/contains → fuzzy.
"""
import os
import re
from difflib import get_close_matches
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ["ALMM_TABLE"]
ddb        = boto3.resource("dynamodb")
table      = ddb.Table(TABLE_NAME)

# ── brand list cache (populated on first call, reused on warm invocations) ────
_ALL_BRANDS: list[str] = []


def _load_brands() -> list[str]:
    global _ALL_BRANDS
    if _ALL_BRANDS:
        return _ALL_BRANDS
    print("[check_almm] Loading brand list from DynamoDB (cold start)...")
    brands = set()
    kwargs = {"ProjectionExpression": "brand_normalized"}
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            brands.add(item["brand_normalized"])
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    _ALL_BRANDS = sorted(brands)
    print(f"[check_almm] Loaded {len(_ALL_BRANDS)} brands")
    return _ALL_BRANDS


# ── brand normalization (matches parse_almm_pdf.py logic) ─────────────────────

def _normalize(name: str) -> str:
    if not name:
        return ""
    s = str(name).replace("\n", " ").lower()
    s = re.sub(r"^m[/\.]?s\.?\s*", "", s)       # strip M/s
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s.strip("_")


# ── DynamoDB lookup ────────────────────────────────────────────────────────────

def _query_brand(brand_norm: str) -> list[dict]:
    resp = table.query(KeyConditionExpression=Key("brand_normalized").eq(brand_norm))
    return resp.get("Items", [])


def _find_brand(raw_brand: str) -> tuple[str, list[dict]]:
    """
    Try multiple strategies to find the brand in DynamoDB.
    Returns (matched_brand_norm, items).
    """
    norm = _normalize(raw_brand)
    if not norm:
        return "", []

    # 1. Exact match
    items = _query_brand(norm)
    if items:
        return norm, items

    all_brands = _load_brands()

    # 2. Prefix: query brand starts with our norm (e.g. "waaree" → "waaree_energies_limited")
    prefix_match = [b for b in all_brands if b.startswith(norm) or norm in b]
    if prefix_match:
        best = prefix_match[0]
        items = _query_brand(best)
        if items:
            return best, items

    # 3. First word match (e.g. "vikram" matches "vikram_solar_pvt_ltd")
    first_word = norm.split("_")[0]
    if len(first_word) >= 4:
        word_match = [b for b in all_brands if b.startswith(first_word)]
        if word_match:
            best = word_match[0]
            items = _query_brand(best)
            if items:
                return best, items

    # 4. Fuzzy match (last resort)
    fuzzy = get_close_matches(norm, all_brands, n=1, cutoff=0.75)
    if fuzzy:
        best = fuzzy[0]
        items = _query_brand(best)
        if items:
            return best, items

    return norm, []


# ── watt range check ───────────────────────────────────────────────────────────

def _watt_in_range(item: dict, watt: float) -> bool:
    try:
        lo = float(item.get("watt_range_min") or 0)
        hi = float(item.get("watt_range_max") or 9999)
        return lo <= watt <= hi
    except Exception:
        return True   # if range unknown, don't disqualify


# ── main function ──────────────────────────────────────────────────────────────

def check_almm(brand: str, model: Optional[str], system_kw: float) -> dict:
    """
    Check ALMM DCR status for a panel brand/model.
    Returns dict with: dcr_status, detail, matched_brand, list_version
    """
    if not brand or len(brand) < 2:
        return {
            "dcr_status": "UNCERTAIN",
            "detail":     "Panel brand not readable from quote. Ask vendor for ALMM certificate.",
            "matched_brand": None,
            "list_version":  "ALMM List-I (Modules)",
        }

    matched_norm, items = _find_brand(brand)

    if not items:
        return {
            "dcr_status": "UNCERTAIN",
            "detail":     f"Brand '{brand}' not found in ALMM database. Ask vendor for MNRE ALMM certificate before signing.",
            "matched_brand": None,
            "list_version":  "ALMM List-I (Modules)",
        }

    # Estimate watt per panel (rough: 3kW system ≈ 6×500W panels)
    # Use watt from model string if available
    watt = _extract_watt_from_model(model) if model else (system_kw * 1000 / 6)

    # Find matching items by watt range
    range_match = [i for i in items if _watt_in_range(i, watt)]
    check_items = range_match if range_match else items[:3]

    # All items on ALMM List-I are DCR certified — that's what the list IS.
    # But if the DB has dcr_certified=False for any reason, flag it.
    any_dcr = any(i.get("dcr_certified", True) for i in check_items)

    brand_display  = check_items[0].get("brand_display", brand)
    list_version   = check_items[0].get("list_version", "ALMM List-I")
    matched_model  = check_items[0].get("model_prefix", "") if range_match else None

    if any_dcr:
        detail = (
            f"{brand_display} panels found in {list_version}. "
            f"DCR certified — eligible for PM Surya Ghar subsidy."
        )
        if matched_model:
            detail = f"{brand_display} {matched_model.upper()} found in {list_version}. DCR certified ✓"
        return {
            "dcr_status":    "PASS",
            "detail":        detail,
            "matched_brand": brand_display,
            "list_version":  list_version,
        }
    else:
        return {
            "dcr_status":    "FAIL",
            "detail":        f"{brand_display} panels in this watt range are NOT DCR certified. Installing these will result in PM Surya Ghar subsidy rejection.",
            "matched_brand": brand_display,
            "list_version":  list_version,
        }


def _extract_watt_from_model(model_str: str) -> float:
    """Extract watt from model string like 'WS-540M' → 540.0"""
    import re
    # Parenthesised: (540 Wp)
    m = re.search(r"\((\d+)\s*[Ww][Pp]?\)", model_str)
    if m:
        return float(m.group(1))
    # Inline number 300-1000
    nums = re.findall(r"\d+", model_str)
    valid = [int(n) for n in nums if 200 <= int(n) <= 1000]
    return float(max(valid)) if valid else 400.0
