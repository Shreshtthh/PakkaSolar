"""
backend/audit_worker/tools/calc_subsidy.py
"""


# States that get 10% additional subsidy under PM Surya Ghar
SPECIAL_CATEGORY_STATES = {"HP", "JK", "UK", "NE", "MZ", "NL", "MN", "TR", "AR", "SK", "MG"}


def calc_subsidy(system_kw: float, state: str = "HP") -> dict:
    """
    Calculate PM Surya Ghar subsidy.
    
    Rates (pmsuryaghar.gov.in):
      - First 2 kW : ₹30,000/kW
      - 3rd kW     : ₹18,000/kW
      - Cap (general)       : ₹78,000
      - Cap (special states): ₹85,800 (10% extra)
    """
    multiplier = 1.10 if state in SPECIAL_CATEGORY_STATES else 1.00

    kw = min(system_kw, 3.0)   # subsidy only up to 3 kW
    if kw <= 2.0:
        base = kw * 30_000
    else:
        base = 2 * 30_000 + (kw - 2.0) * 18_000

    cap     = 78_000 * multiplier
    subsidy = min(base * multiplier, cap)

    breakdown = (
        f"₹{2*30000:,} for first 2 kW + ₹{18000:,} for 3rd kW"
        if system_kw >= 3 else
        f"₹{int(system_kw*30000):,} for {system_kw} kW"
    )
    if state in SPECIAL_CATEGORY_STATES:
        breakdown += f" + 10% {state} special category bonus"

    return {
        "subsidy_amount":  int(subsidy),
        "eligible":        True,
        "state":           state,
        "breakdown":       breakdown,
        "cap":             int(cap),
        "system_kw_used":  kw,
        "note": "Subsidy requires DCR-certified panels and empanelled vendor. Lost if non-DCR panels installed.",
    }
