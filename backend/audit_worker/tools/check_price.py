"""
backend/audit_worker/tools/check_price.py
"""


# MNRE benchmark price ranges ₹/kW (HP, special category, 3kW system)
BENCHMARK = {
    "HP": {"low": 50_000, "high": 70_000},
    "default": {"low": 48_000, "high": 68_000},
}


def check_price(quoted_price: int, system_kw: float, state: str = "HP") -> dict:
    """
    Check if quoted price is within MNRE benchmark range.
    Returns: status (PASS/AMBER/FAIL), price_per_kw, detail
    """
    if not quoted_price or quoted_price <= 0:
        return {
            "status":        "UNCERTAIN",
            "price_per_kw":  None,
            "detail":        "Total price not readable from quote. Get a detailed itemised quote from vendor.",
        }

    if system_kw <= 0:
        system_kw = 3.0

    price_per_kw  = quoted_price / system_kw
    bench         = BENCHMARK.get(state, BENCHMARK["default"])
    bench_low     = bench["low"]
    bench_high    = bench["high"]

    formatted_pkw = f"₹{int(price_per_kw):,}/kW"
    bench_str     = f"₹{bench_low:,}–₹{bench_high:,}/kW"

    if price_per_kw < bench_low * 0.80:
        # Suspiciously low — likely non-DCR panels
        status = "AMBER"
        detail = (
            f"Price {formatted_pkw} is unusually LOW (benchmark: {bench_str}). "
            "This may indicate cheap, non-DCR panels that will fail the subsidy inspection."
        )
    elif price_per_kw > bench_high * 1.25:
        # Clearly overpriced
        status = "AMBER"
        detail = (
            f"Price {formatted_pkw} is above MNRE benchmark {bench_str}. "
            "Negotiate or get 2–3 quotes from other empanelled vendors."
        )
    elif bench_low <= price_per_kw <= bench_high:
        status = "PASS"
        detail = f"Price {formatted_pkw} is within MNRE benchmark {bench_str}. ✓"
    else:
        # In range but at the edges
        status = "PASS"
        detail = f"Price {formatted_pkw} is close to MNRE benchmark {bench_str}. Acceptable."

    return {
        "status":       status,
        "price_per_kw": int(price_per_kw),
        "total_price":  quoted_price,
        "detail":       detail,
        "benchmark":    bench_str,
    }
