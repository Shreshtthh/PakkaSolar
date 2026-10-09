"""
backend/audit_worker/tools/check_vendor.py
"""
import os
import re
from difflib import get_close_matches
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ["VENDORS_TABLE"]
ddb        = boto3.resource("dynamodb")
table      = ddb.Table(TABLE_NAME)

_VENDOR_CACHE: dict[str, list] = {}   # state_code → [vendor_norms]


def _normalize_vendor(name: str) -> str:
    if not name:
        return ""
    s = name.lower()
    # Strip common suffixes
    for suffix in ["pvt ltd", "private limited", "pvt. ltd.", "& sons",
                   "and sons", "enterprises", "trading co", "traders", "solar"]:
        s = s.replace(suffix, "")
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s.strip("_")


def _load_vendors(state: str) -> list[str]:
    if state in _VENDOR_CACHE:
        return _VENDOR_CACHE[state]
    resp = table.query(
        KeyConditionExpression=Key("state_code").eq(state),
        ProjectionExpression="vendor_name_normalized",
    )
    vendors = [i["vendor_name_normalized"] for i in resp.get("Items", [])]
    _VENDOR_CACHE[state] = vendors
    return vendors


def check_vendor(vendor_name: str, state: str = "HP") -> dict:
    if not vendor_name or len(vendor_name) < 2:
        return {
            "status":  "NOT_FOUND",
            "detail":  "Vendor name not readable from quote. Verify empanelment at pmsuryaghar.gov.in.",
            "matched": None,
        }

    norm = _normalize_vendor(vendor_name)
    all_vendors = _load_vendors(state)

    if not all_vendors:
        return {
            "status":  "NOT_FOUND",
            "detail":  f"No vendor data for state {state}. Check pmsuryaghar.gov.in manually.",
            "matched": None,
        }

    # 1. Exact match
    if norm in all_vendors:
        return _fetch_vendor_record(norm, state, vendor_name)

    # 2. Contains / prefix match
    contains = [v for v in all_vendors if norm in v or v in norm]
    if contains:
        return _fetch_vendor_record(contains[0], state, vendor_name)

    # 3. Fuzzy match
    fuzzy = get_close_matches(norm, all_vendors, n=1, cutoff=0.70)
    if fuzzy:
        return _fetch_vendor_record(fuzzy[0], state, vendor_name)

    return {
        "status":  "NOT_FOUND",
        "detail":  f"'{vendor_name}' not found in {state} vendor registry. Verify at pmsuryaghar.gov.in before signing.",
        "matched": None,
    }


def _fetch_vendor_record(vendor_norm: str, state: str, raw_name: str) -> dict:
    resp = table.get_item(Key={"state_code": state, "vendor_name_normalized": vendor_norm})
    item = resp.get("Item", {})
    empanelled    = item.get("empanelled", True)
    vendor_display = item.get("vendor_display", raw_name)
    discom        = item.get("discom", f"{state}SEBL")

    if empanelled:
        return {
            "status":  "PASS",
            "detail":  f"{vendor_display} is empanelled under PM Surya Ghar ({discom}). ✓",
            "matched": vendor_display,
        }
    else:
        return {
            "status":  "FAIL",
            "detail":  f"{vendor_display} is NOT empanelled under PM Surya Ghar. You cannot claim subsidy using this vendor.",
            "matched": vendor_display,
        }
