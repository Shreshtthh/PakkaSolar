"""
parse_almm_pdf.py  (v2 — revised for actual ALMM List-I PDF structure)
------------------------------------------------------------------------
Handles:
  • "Name of the Manufacturer" merged cells → forward-fill brand
  • "Applied Model" column containing embedded wattage, e.g. "SPS156GG640 (640 Wp)"
  • "Enlisted Models" column (comma/newline-separated list of certified variants)
  • "Type of Module" instead of "Cell Type"

Usage:
    python scripts/parse_almm_pdf.py --pdf ALMM-list-1.pdf --out scripts/seed_data/almm_panels.csv

Install deps:
    pip install pdfplumber pandas
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

# ── column aliases ─────────────────────────────────────────────────────────────
# Maps every known PDF header variant → our internal canonical name.
COL_ALIASES = {
    # ── Manufacturer
    "name of the manufacturer":   "brand_display",
    "name of manufacturer":       "brand_display",
    "name of company":            "brand_display",
    "manufacturer":               "brand_display",
    "company name":               "brand_display",
    "manufacturer name":          "brand_display",

    # ── Applied / base model (may embed wattage)
    "applied model":              "applied_model",
    "applied model no":           "applied_model",
    "applied model no.":          "applied_model",

    # ── Enlisted / certified variant list
    "enlisted models":            "enlisted_models",
    "enlisted model":             "enlisted_models",
    "enlisted model no":          "enlisted_models",
    "enlisted model no.":         "enlisted_models",
    "enlisted model nos.":        "enlisted_models",

    # ── Legacy / alternate model column names
    "model no":                   "model_raw",
    "model no.":                  "model_raw",
    "model number":               "model_raw",
    "module model no":            "model_raw",
    "module model no.":           "model_raw",
    "module model number":        "model_raw",
    "series":                     "model_raw",
    "model no / series":          "model_raw",
    "module model no./series":    "model_raw",

    # ── Wattage (standalone column, if it exists)
    "rated power":                "watt_peak",
    "watt peak":                  "watt_peak",
    "module wattage":             "watt_peak",
    "power (wp)":                 "watt_peak",
    "power(wp)":                  "watt_peak",
    "wp":                         "watt_peak",
    "capacity (wp)":              "watt_peak",

    # ── Cell / module type
    "type of module":             "cell_type",
    "module type":                "cell_type",
    "cell type":                  "cell_type",
    "cell technology":            "cell_type",
    "technology":                 "cell_type",

    # ── Serial number (skip)
    "s.no":                       "sr_no",
    "s.no.":                      "sr_no",
    "sr.no":                      "sr_no",
    "sr. no.":                    "sr_no",
    "sno":                        "sr_no",
    "s no":                       "sr_no",
    "sl.no.":                     "sr_no",
    "sl. no.":                    "sr_no",
}

# ── header keywords that positively identify a header row
HEADER_SIGNALS = {"brand_display", "model_raw", "applied_model", "enlisted_models"}

# ── text to ignore when deciding if a brand cell is empty
_BLANK_RE = re.compile(r"^[\s\-–—]*$")


def normalize_col(name: str) -> str:
    if name is None:
        return ""
    cleaned = re.sub(r"\s+", " ", str(name).strip().lower())
    return COL_ALIASES.get(cleaned, cleaned)


# ── annotation phrases that appear as sub-rows in the PDF ────────────────────
# Rows whose brand cell contains any of these are section dividers, not brands.
ANNOTATION_KEYWORDS = [
    "model addition", "capacity addition", "new addition",
    "capacity change", "change in model", "addition in almm",
    "model change", "renewal", "new entrant", "fresh addition",
]


def normalize_brand(name: str) -> str:
    if not name:
        return ""
    # Replace newlines that pdfplumber emits for multi-line cells
    s = str(name).replace("\n", " ").lower()
    # Strip common Indian business prefix "M/s", "Ms.", "M.s."
    s = re.sub(r"^m[/\.]?s\.?\s+", "", s)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s.strip("_")


def is_blank(val: str) -> bool:
    return not val or bool(_BLANK_RE.match(val))


# ── wattage extraction ─────────────────────────────────────────────────────────

def extract_watt_from_string(text: str):
    """
    Pull wattage from strings like:
        "SPS156GG640 (640 Wp)"      → 640, 640
        "WS-540M (540Wp)"           → 540, 540
        "500-600 Wp"                → 500, 600
        "320/330/340"               → 320, 340
        "400Wp"                     → 400, 400
        "SPM 72H 390-415"           → 390, 415
    Returns (watt_min, watt_max) or (None, None).
    """
    if not text:
        return None, None

    # Pattern 1: parenthesised value  e.g. "(640 Wp)" or "(640Wp)"
    m = re.search(r"\((\d+(?:\.\d+)?)\s*[Ww][Pp]?\)", text)
    if m:
        w = int(float(m.group(1)))
        return w, w

    # Pattern 2: dash / "to" range  e.g. "390-415" or "390 to 415"
    m = re.search(r"(\d{3,4})\s*(?:-|to)\s*(\d{3,4})", text)
    if m:
        return int(m.group(1)), int(m.group(2))

    # Pattern 3: inline Wp  e.g. "540Wp", "540 Wp", "540W"
    m = re.search(r"(\d{3,4})\s*[Ww][Pp]?(?:\b|$)", text)
    if m:
        w = int(m.group(1))
        return w, w

    # Pattern 4 (REMOVED): slash-separated list was incorrectly treating
    # solar cell counts (e.g. 108, 120 cells/module) as watt values.
    # The three patterns above are sufficient for all real watt formats.

    return None, None


def parse_watt_range(raw: str):
    """For a standalone watt column (if it exists)."""
    return extract_watt_from_string(raw)


# ── split enlisted models string ───────────────────────────────────────────────

def split_models(text: str) -> list[str]:
    """
    Split an 'Enlisted Models' cell into individual model strings.
    Handles comma, semicolon, newline, and slash as delimiters.
    """
    if not text:
        return []
    # Split on comma, semicolon, newline, or bare slash not inside parens
    parts = re.split(r"[,;\n]+", text)
    result = []
    for p in parts:
        p = p.strip()
        if p and len(p) >= 2:
            result.append(p)
    return result


# ── model_prefix from a model string ──────────────────────────────────────────

def model_prefix(model_str: str) -> str:
    """
    Derive a short prefix key from a model string for DynamoDB SK.
    E.g. "SPS156GG640 (640 Wp)" → "sps156gg640"
         "WS-540M"              → "ws-540m"
    Strip parenthesised wattage, lowercase, collapse whitespace.
    """
    if not model_str:
        return "unknown"
    s = re.sub(r"\(.*?\)", "", model_str)   # remove (640 Wp)
    s = s.strip().lower()
    s = re.sub(r"\s+", "_", s)
    return s[:60]  # DynamoDB SK length sanity


# ── table extraction ───────────────────────────────────────────────────────────

def extract_tables(pdf_path: str) -> list[dict]:
    """
    Extract rows from all tables in the PDF.
    Applies forward-fill for merged 'brand_display' and 'cell_type' cells.
    Returns a list of dicts keyed by canonical column names.
    """
    all_rows = []
    current_header = None
    last_brand = ""       # ← forward-fill state for manufacturer
    last_cell_type = ""   # ← forward-fill state for module type

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                if not table:
                    continue

                for raw_row in table:
                    if not raw_row or all(c is None for c in raw_row):
                        continue

                    # Replace \n inside cells (pdfplumber returns multi-line
                    # cell content with embedded newlines)
                    cells = [
                        str(c).replace("\n", " ").strip() if c is not None else ""
                        for c in raw_row
                    ]
                    norm = [normalize_col(c) for c in cells]

                    # ── detect header row ──────────────────────────────────
                    if any(sig in norm for sig in HEADER_SIGNALS):
                        current_header = norm
                        last_brand = ""      # reset on new table section
                        last_cell_type = ""
                        continue

                    if current_header is None:
                        continue

                    # ── map cells → dict ───────────────────────────────────
                    rec = dict(zip(current_header, cells))

                    # ── clean & forward-fill brand ─────────────────────────
                    brand_val = rec.get("brand_display", "")
                    brand_val = brand_val.replace("\n", " ")

                    # Strip "M/s " or "M/s. " from the beginning
                    brand_val = re.sub(r"(?i)^m/s\.?\s*", "", brand_val)

                    # Strip parenthesised ALMM admin notes anywhere in the string
                    # e.g. "(Model Addition)", "(Co-ALMM)", "(Renewal)"
                    brand_val = re.sub(
                        r"\(.*?(?:Addition|Renewal|Change|ALMM|Co-ALMM).*?\)",
                        "", brand_val, flags=re.IGNORECASE
                    )

                    # Catch bare "Co-ALMM" / "co-almm" not inside parens
                    brand_val = re.sub(r"(?i)co-almm.*", "", brand_val).strip()

                    if is_blank(brand_val):
                        rec["brand_display"] = last_brand
                    else:
                        last_brand = brand_val
                        rec["brand_display"] = brand_val

                    if is_blank(rec.get("brand_display", "")):
                        continue   # truly no brand even after forward-fill

                    # ── forward-fill cell_type ─────────────────────────────
                    ct_val = rec.get("cell_type", "")
                    if is_blank(ct_val):
                        rec["cell_type"] = last_cell_type
                    else:
                        last_cell_type = ct_val
                        rec["cell_type"] = ct_val

                    all_rows.append(rec)

        if not all_rows:
            print(f"  (no table rows found after {total_pages} pages)")

    return all_rows


def extract_text_fallback(pdf_path: str) -> list[dict]:
    """
    Fallback for PDFs where table extraction returns nothing.
    Tries to parse lines that look like data rows.
    This is best-effort; the CSV will need manual cleanup.
    """
    rows = []
    last_brand = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # Heuristic: starts with a serial number
                if re.match(r"^\d{1,4}[\.\s]", line):
                    rows.append({"raw_line": line, "brand_display": last_brand})
                elif len(line) > 5 and not re.search(r"\d", line):
                    # Possibly a standalone brand name line
                    last_brand = line

    return rows


# ── build output records ───────────────────────────────────────────────────────

def records_from_row(rec: dict) -> list[dict]:
    """
    Convert one raw extracted row into 1-N output records.
    One record per certified model variant (applied_model + enlisted_models).
    """
    brand_raw = rec.get("brand_display", "").replace("\n", " ").strip()
    if is_blank(brand_raw) or len(brand_raw) < 3:
        return []

    brand_lower = brand_raw.lower()

    # Skip obvious header-bleed rows (column names leaking into data)
    if any(kw in brand_lower for kw in
           ["s.no", "sr.no", "manufacturer", "model no", "name of", "enlisted", "applied"]):
        return []

    # Skip PDF annotation sub-rows (e.g. "(Model Addition)", "(Capacity Addition)")
    if any(kw in brand_lower for kw in ANNOTATION_KEYWORDS):
        return []

    brand_norm = normalize_brand(brand_raw)
    if not brand_norm:
        return []

    cell_type = rec.get("cell_type", "").strip() or "Unknown"

    # Collect all model strings from both columns
    applied   = rec.get("applied_model", rec.get("model_raw", "")).strip()
    enlisted  = rec.get("enlisted_models", "").strip()
    watt_col  = rec.get("watt_peak", "").strip()   # standalone watt column (may be absent)

    model_strings = []

    if applied:
        model_strings.append(applied)

    for m in split_models(enlisted):
        if m and m != applied:
            model_strings.append(m)

    # If we got nothing at all, still emit one "unknown" record so the brand is seeded
    if not model_strings:
        model_strings = ["unknown"]

    # Pre-extract watt from the parent "applied" model string so enlisted
    # siblings can inherit it (Fallback 1 below)
    applied_wmin, applied_wmax = extract_watt_from_string(applied)
    if applied_wmin is None:
        applied_wmin, applied_wmax = parse_watt_range(watt_col)

    out = []
    for model_str in model_strings:
        # Level 1 — explicit wattage tag in this model string e.g. "(390 Wp)"
        wmin, wmax = extract_watt_from_string(model_str)

        # Level 2 — max-integer heuristic on the model string itself.
        # "aspl390mp108" → numbers are [390, 108] → largest plausible = 390 W.
        # Must run BEFORE parent inheritance so each model uses its own code.
        if wmin is None:
            nums = re.findall(r"\d+", model_str)
            valid_watts = [int(n) for n in nums if 30 <= int(n) <= 1000]
            if valid_watts:
                wmin = wmax = max(valid_watts)

        # Level 3 — last resort: inherit watt from parent applied_model row.
        # Only fires when the model string has no digits at all (rare).
        if wmin is None:
            wmin, wmax = applied_wmin, applied_wmax

        out.append({
            "brand_display":    brand_raw,
            "brand_normalized": brand_norm,
            "model_raw":        model_str,
            "model_prefix":     model_prefix(model_str),
            "cell_type":        cell_type,
            "watt_peak_raw":    model_str if wmin else watt_col,
            "watt_range_min":   wmin,
            "watt_range_max":   wmax,
            # Every entry on ALMM List-I IS DCR certified — that's the whole point
            "dcr_certified":    True,
            "list_name":        "ALMM List-I (Modules)",
            "list_version":     "v2026",
        })

    return out


def build_dataframe(raw_rows: list[dict]) -> pd.DataFrame:
    records = []
    for row in raw_rows:
        records.extend(records_from_row(row))

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Remove exact duplicates (same brand + model_prefix)
    df = df.drop_duplicates(subset=["brand_normalized", "model_prefix"])
    df = df.sort_values(["brand_normalized", "model_prefix"]).reset_index(drop=True)
    return df


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf",  required=True, help="Path to ALMM-list-1.pdf")
    parser.add_argument("--out",  required=True, help="Output CSV path")
    parser.add_argument("--debug", action="store_true",
                        help="Print every raw extracted row (useful for diagnosing new PDF formats)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        print(f"ERROR: PDF not found at {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Opening {pdf_path} ...")

    raw_rows = extract_tables(str(pdf_path))
    method = "table"

    if len(raw_rows) < 5:
        print(f"Table extraction returned only {len(raw_rows)} rows — trying text fallback.")
        raw_rows = extract_text_fallback(str(pdf_path))
        method = "text"

    print(f"Extracted {len(raw_rows)} raw rows via '{method}' method.")

    if args.debug:
        print("\n── DEBUG: first 10 raw rows ──────────────────────────────")
        for r in raw_rows[:10]:
            print(r)
        print("──────────────────────────────────────────────────────────\n")

    df = build_dataframe(raw_rows)

    if df.empty:
        print("\n⚠️  Output DataFrame is empty.")
        print("   Possible reasons:")
        print("   1. The PDF is image-based (scanned) — pdfplumber can't read images.")
        print("   2. Column headers in the PDF don't match any known alias.")
        print("      Run with --debug to see the raw extracted rows and identify header names.")
        print("   3. All rows were filtered out (check brand filter conditions).")
        print()
        print("   Fallback: use scripts/seed_data/almm_panels_fallback.csv")
        print("   → cp scripts/seed_data/almm_panels_fallback.csv scripts/seed_data/almm_panels.csv")
        sys.exit(1)

    df.to_csv(out_path, index=False)
    print(f"\n✅ Saved {len(df)} records ({df['brand_normalized'].nunique()} brands) to {out_path}")

    print("\nSample output (first 15 rows):")
    display_cols = ["brand_display", "model_prefix", "watt_range_min", "watt_range_max", "cell_type"]
    print(df[display_cols].head(15).to_string(index=False))

    print(f"\nRecords per brand (top 15):")
    print(df.groupby("brand_normalized")["model_prefix"]
            .count()
            .sort_values(ascending=False)
            .head(15)
            .to_string())


if __name__ == "__main__":
    main()
