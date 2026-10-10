"""
backend/audit_worker/polly.py
-------------------------------
Generates Hindi/English voice notes via Amazon Polly → S3.
"""
import os

import boto3

BUCKET = os.environ["MEDIA_BUCKET"]
polly  = boto3.client("polly")
s3     = boto3.client("s3")

# Base URL for public verdict files (S3 bucket with public read on verdicts/)
S3_BASE_URL = f"https://{os.environ.get('MEDIA_BUCKET', 'pakkasolar-media')}.s3.amazonaws.com"


def _build_text(verdict: dict, lang: str) -> str:
    """Build the Polly speech text from verdict data."""
    v      = verdict.get("verdict", "AMBER")
    checks = verdict.get("checks", {})
    sub    = verdict.get("subsidy", {})

    dcr_status    = checks.get("panel_dcr", {}).get("dcr_status", "UNCERTAIN")
    vendor_status = checks.get("vendor", {}).get("status", "NOT_FOUND")
    subsidy_amt   = sub.get("subsidy_amount", 85800)
    subsidy_str   = f"{subsidy_amt:,}"

    if lang == "hi":
        if v == "RED":
            return (
                f"Namaste. PakkaSolar ki taraf se aapke solar quote ki jaanch poori ho gayi hai. "
                f"Hamare AI ne paaya ki aapke quote mein likhe solar panels, Sarkar ki ALMM approved list mein nahi hain. "
                f"Iska matlab hai, agar yahi panels lagaye gaye, toh aapko {subsidy_str} rupaye ki PM Surya Ghar subsidy nahi milegi. "
                f"Abhi apne vendor se kehein: Mujhe ALMM certified, DCR approved panels ka revised quote chahiye. "
                f"Bina DCR panels ke, aapka paisa doob sakta hai. "
                f"PakkaSolar ke saath, sign karne se pehle jaanch karein."
            )
        elif v == "AMBER":
            return (
                f"Namaste. PakkaSolar ki taraf se aapke quote ki jaanch mein kuch sawaal hain. "
                f"Kuch cheezein unclear hain. Apne vendor se confirm karein ki panels ALMM certified hain, "
                f"aur vendor PM Surya Ghar portal par registered hai. "
                f"Jab tak confirmation nahi milti, sign mat karein."
            )
        else:  # GREEN
            return (
                f"Namaste. PakkaSolar ki taraf se khushkhabri! "
                f"Aapke solar quote ki jaanch safal rahi. "
                f"Panels DCR certified hain. Vendor registered hai. Price bhi theek hai. "
                f"Aap {subsidy_str} rupaye ki subsidy ke liye eligible hain. "
                f"Congratulations, aage badh sakte hain."
            )
    else:
        if v == "RED":
            return (
                f"Hello. PakkaSolar has completed your solar quote audit. "
                f"We found that the panels in your quote are NOT on MNRE's approved ALMM list. "
                f"This means you will NOT receive the {subsidy_str} rupee PM Surya Ghar subsidy if these panels are installed. "
                f"Ask your vendor for a revised quote with ALMM certified DCR panels immediately. "
                f"Check before you sign."
            )
        elif v == "AMBER":
            return (
                f"Hello. PakkaSolar has some concerns about your solar quote. "
                f"Some details could not be verified. Ask your vendor to confirm panel certification and vendor registration "
                f"before proceeding."
            )
        else:
            return (
                f"Hello. Good news from PakkaSolar! "
                f"Your solar quote passed our audit. DCR certified panels, registered vendor, fair price. "
                f"You are eligible for {subsidy_str} rupees in PM Surya Ghar subsidy. "
                f"You're good to proceed."
            )


def generate_voice_note(verdict: dict, audit_id: str, lang: str = "hi") -> str:
    """
    Synthesize speech via Amazon Polly and save to S3.
    Returns the public S3 URL for the MP3.
    """
    text = _build_text(verdict, lang)

    # Voice selection
    if lang == "hi":
        voice_id  = "Kajal"    # Only neural Hindi voice
        lang_code = "hi-IN"
    else:
        voice_id  = "Joanna"
        lang_code = "en-US"

    resp = polly.synthesize_speech(
        Engine="neural",
        LanguageCode=lang_code,
        VoiceId=voice_id,
        Text=text,
        OutputFormat="mp3",
        TextType="text",
    )

    key = f"verdicts/{audit_id}.mp3"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=resp["AudioStream"].read(),
        ContentType="audio/mpeg",
    )

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=604800, # 7 days
    )
    print(f"[polly] Voice note saved: {url}")
    return url
