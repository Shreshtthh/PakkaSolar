"""
backend/audit_worker/tools/parse_quote.py
------------------------------------------
Calls Bedrock Nova Pro multimodal to extract fields from a solar quote image.
"""
import base64
import json
import os
import re
from typing import Optional

import boto3
from pydantic import BaseModel, field_validator

# ── Custom ENV Loader for Hackathon Workaround ─────────────────────────────────
def load_local_env():
    """Load old keys from a local .env file so we don't commit them to GitHub."""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip()

load_local_env()

BUCKET         = os.environ.get("MEDIA_BUCKET", "local")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
MODEL_ID       = "us.amazon.nova-lite-v1:0"    # cross-region inference profile
MOCK_MODE      = os.environ.get("MOCK_MODE", "false").lower() == "true"

s3 = boto3.client("s3")

# Only inject explicit keys for Bedrock if they exist in the environment
old_ak = os.environ.get("OLD_AWS_ACCESS_KEY_ID")
old_sk = os.environ.get("OLD_AWS_SECRET_ACCESS_KEY")
if old_ak and old_sk:
    print("[parse_quote] Using OLD AWS credentials for Bedrock client.")
    bedrock = boto3.client(
        "bedrock-runtime", 
        region_name=BEDROCK_REGION,
        aws_access_key_id=old_ak,
        aws_secret_access_key=old_sk
    )
else:
    bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)


# ── Pydantic schema ────────────────────────────────────────────────────────────

class QuoteExtraction(BaseModel):
    system_kw:    float
    brand:        Optional[str] = None
    model:        Optional[str] = None
    vendor_name:  Optional[str] = None
    quoted_price: Optional[int] = None
    warranty_years: Optional[int] = None

    @field_validator("system_kw", mode="before")
    @classmethod
    def coerce_kw(cls, v):
        if v is None:
            return 3.0
        return float(v)

    @field_validator("quoted_price", mode="before")
    @classmethod
    def coerce_price(cls, v):
        if v is None:
            return None
        # Strip commas / currency symbols
        if isinstance(v, str):
            v = v.replace(",", "").replace("₹", "").replace("Rs", "").strip()
        try:
            return int(float(v))
        except Exception:
            return None

    @field_validator("warranty_years", mode="before")
    @classmethod
    def coerce_warranty(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            nums = re.findall(r"\d+", v)
            return int(nums[0]) if nums else None
        try:
            return int(v)
        except Exception:
            return None


# ── prompt ─────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """You are reading an Indian residential rooftop solar quote document.

Extract ONLY the following fields and return EXACTLY valid JSON with no other text:
{
  "system_kw": <number — total kW capacity of the solar system>,
  "brand": "<solar panel brand name, e.g. Waaree, Adani Solar, Vikram Solar>",
  "model": "<panel model number if visible, else null>",
  "vendor_name": "<name of the company/vendor issuing this quote>",
  "quoted_price": <total quoted price in Indian Rupees as integer, no commas>,
  "warranty_years": <performance warranty years if stated, else null>
}

Rules:
- If a field is not clearly visible, set it to null. Do NOT guess.
- system_kw must be a number (e.g. 3 or 3.0).
- quoted_price must be an integer (remove ₹ and commas).
- Return ONLY the JSON object. No markdown, no explanation.
"""


# ── main function ──────────────────────────────────────────────────────────────

def parse_quote(s3_key: str) -> dict:
    """
    Extract solar quote fields from an image in S3.
    Returns a dict matching QuoteExtraction schema.
    """
    if MOCK_MODE:
        print("[parse_quote] MOCK MODE — returning hardcoded quote")
        return _mock_extraction()

    # Pull image from S3
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=s3_key)
        img_bytes = obj["Body"].read()
    except Exception as e:
        raise RuntimeError(f"Failed to read image from S3 ({s3_key}): {e}")

    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    # Determine image format from key or default to jpeg
    fmt = "jpeg"
    if s3_key.lower().endswith(".png"):
        fmt = "png"
    elif s3_key.lower().endswith(".webp"):
        fmt = "webp"

    # Build Nova multimodal request
    request_body = {
        "messages": [{
            "role": "user",
            "content": [
                {
                    "image": {
                        "format": fmt,
                        "source": {"bytes": img_b64},
                    }
                },
                {"text": EXTRACTION_PROMPT},
            ],
        }],
        "inferenceConfig": {
            "maxTokens": 512,
            "temperature": 0.0,   # deterministic extraction
            "topP": 1.0,
        },
    }

    # Invoke Bedrock
    try:
        resp = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json",
        )
        raw = json.loads(resp["body"].read())
        text = raw["output"]["message"]["content"][0]["text"].strip()
    except Exception as e:
        raise RuntimeError(f"Bedrock Nova invocation failed: {e}")

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    # Parse JSON
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"Nova returned non-JSON: {text[:300]}")
        # Try to extract JSON from the response
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            parsed = json.loads(m.group(0))
        else:
            raise RuntimeError(f"Could not parse JSON from Nova response: {e}")

    # Validate with Pydantic
    try:
        validated = QuoteExtraction(**parsed)
    except Exception as e:
        print(f"Pydantic validation warning: {e} — using raw parsed dict")
        validated = QuoteExtraction(
            system_kw=parsed.get("system_kw") or 3.0,
            brand=parsed.get("brand"),
            model=parsed.get("model"),
            vendor_name=parsed.get("vendor_name"),
            quoted_price=parsed.get("quoted_price"),
            warranty_years=parsed.get("warranty_years"),
        )

    print(f"[parse_quote] Extracted: {validated.model_dump()}")
    return validated.model_dump()


def _mock_extraction() -> dict:
    """Hardcoded quote for local testing without Bedrock."""
    return {
        "system_kw":      3.0,
        "brand":          "Waaree Energies",
        "model":          "WS-540M",
        "vendor_name":    "Cheapo Solar Traders",
        "quoted_price":   140000,
        "warranty_years": 10,
    }
