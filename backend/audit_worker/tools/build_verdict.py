"""
backend/audit_worker/tools/build_verdict.py
"""


SUMMARIES = {
    "RED": {
        "hi": "⚠️ सावधान! आपकी सब्सिडी खतरे में है। ये पैनल MNRE की अप्रूव्ड लिस्ट में नहीं हैं। अभी vendor को बदलें।",
        "en": "⚠️ SUBSIDY AT RISK. The panels quoted are not on MNRE's approved DCR list. Change vendor or panels before signing.",
    },
    "AMBER": {
        "hi": "⚡ कुछ जांच अधूरी है। नीचे दी गई बातें vendor से पूछें और दोबारा check करें।",
        "en": "⚡ SOME CHECKS INCOMPLETE. Ask your vendor the questions below before signing.",
    },
    "GREEN": {
        "hi": "✅ सब कुछ ठीक लग रहा है! DCR certified पैनल, registered vendor, और सही price। आगे बढ़ सकते हैं।",
        "en": "✅ ALL CLEAR! DCR-certified panels, registered vendor, fair price. You're good to proceed.",
    },
}

VENDOR_MESSAGES = {
    "RED": {
        "hi": (
            "Namaste {vendor},\n\n"
            "Mujhe aapka quote mila, lekin mujhe yeh jaanch karni hai:\n\n"
            "• Jo panels aapne quote kiye hain ({brand}), woh MNRE ki ALMM List mein nahi hain.\n"
            "• Bina DCR certified panels ke, PM Surya Ghar ki ₹{subsidy} subsidy nahi milegi.\n\n"
            "Kripya ALMM List-I mein shamil, DCR certified panels ka revised quote bhejein.\n"
            "MNRE approved list: mnre.gov.in/ALMM\n\n"
            "Dhanyavaad"
        ),
        "en": (
            "Hi {vendor},\n\n"
            "I've reviewed your solar quote and have some concerns:\n\n"
            "• The panels quoted ({brand}) are not on MNRE's ALMM approved list.\n"
            "• Without DCR-certified panels, I will not receive the ₹{subsidy} PM Surya Ghar subsidy.\n\n"
            "Please send a revised quote with panels from MNRE's ALMM List-I.\n"
            "Approved list: mnre.gov.in/ALMM\n\n"
            "Thank you"
        ),
    },
    "AMBER": {
        "hi": (
            "Namaste {vendor},\n\n"
            "Aapke quote ke baare mein kuch sawaal hain:\n"
            "1. Kya aapke panels MNRE ALMM List-I mein hain? ALMM certificate bhejein.\n"
            "2. Kya aap PM Surya Ghar portal par registered hain?\n\n"
            "Dhanyavaad"
        ),
        "en": (
            "Hi {vendor},\n\n"
            "I have a few questions about your quote:\n"
            "1. Are your panels on MNRE's ALMM List-I? Please share the ALMM certificate.\n"
            "2. Are you registered on the PM Surya Ghar portal?\n\n"
            "Thank you"
        ),
    },
}


def build_verdict(
    almm_result:   dict,
    vendor_result: dict,
    price_result:  dict,
    subsidy_result: dict,
    gen_result:    dict,
    extracted:     dict,
    lang:          str = "hi",
) -> dict:
    """
    Assemble the final verdict card.
    Returns dict with: verdict (RED/AMBER/GREEN), summary, checks, vendor_message
    """
    dcr_status     = almm_result.get("dcr_status", "UNCERTAIN")
    vendor_status  = vendor_result.get("status", "NOT_FOUND")
    price_status   = price_result.get("status", "UNCERTAIN")

    # ── Determine RAG ──────────────────────────────────────────────────────────
    if dcr_status == "FAIL" or vendor_status == "FAIL":
        verdict = "RED"
    elif dcr_status == "UNCERTAIN" or vendor_status == "NOT_FOUND" or price_status == "AMBER":
        verdict = "AMBER"
    else:
        verdict = "GREEN"

    summaries = SUMMARIES[verdict]
    summary   = summaries.get(lang, summaries["en"])

    # ── Vendor message ─────────────────────────────────────────────────────────
    vendor_name  = extracted.get("vendor_name") or "Solar Vendor"
    brand_name   = extracted.get("brand") or "Unknown Brand"
    subsidy_str  = f"₹{subsidy_result.get('subsidy_amount', 85800):,}"

    msg_templates = VENDOR_MESSAGES.get(verdict, {})
    if msg_templates:
        tmpl = msg_templates.get(lang, msg_templates.get("en", ""))
        vendor_message = tmpl.format(
            vendor=vendor_name,
            brand=brand_name,
            subsidy=subsidy_str,
        )
    else:
        vendor_message = None

    return {
        "verdict":         verdict,
        "summary":         summary,
        "summary_hi":      summaries["hi"],
        "summary_en":      summaries["en"],
        "vendor_message":  vendor_message,
        "checks": {
            "panel_dcr":   almm_result,
            "vendor":      vendor_result,
            "price":       price_result,
        },
        "subsidy":     subsidy_result,
        "generation":  gen_result,
    }
