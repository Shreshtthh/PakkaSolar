"""
backend/audit_worker/lambda_function.py
----------------------------------------
SQS consumer. Runs the full audit pipeline for each message.

Pipeline (sequential, deterministic):
  1. parse_quote   — Bedrock Nova multimodal → extracts quote fields
  2. check_almm    — DynamoDB lookup → DCR certification status
  3. check_vendor  — DynamoDB fuzzy match → empanelment status
  4. calc_subsidy  — pure math → subsidy amount
  5. calc_generation — NASA POWER S3 cache → generation estimate
  6. check_price   — benchmark comparison → price verdict
  7. build_verdict — assembles RAG verdict
  8. polly_voice   — Amazon Polly → Hindi voice note → S3
  9. save_audit    — final result → DynamoDB
"""
import json
import os
import traceback
from datetime import datetime, timezone
from decimal import Decimal

import boto3

from tools.parse_quote   import parse_quote
from tools.check_almm    import check_almm
from tools.check_vendor  import check_vendor
from tools.calc_subsidy  import calc_subsidy
from tools.calc_generation import calc_generation
from tools.check_price   import check_price
from tools.build_verdict import build_verdict
from polly               import generate_voice_note

# ── clients ────────────────────────────────────────────────────────────────────
ddb   = boto3.resource("dynamodb")
TABLE = os.environ["AUDITS_TABLE"]


# ── helpers ────────────────────────────────────────────────────────────────────

def _update_status(audit_id: str, status: str, extra: dict = None):
    """Write status (and optional extra fields) back to DynamoDB."""
    update_expr = "SET #s = :s, updated_at = :u"
    expr_names  = {"#s": "status"}
    expr_values = {
        ":s": status,
        ":u": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        for i, (k, v) in enumerate(extra.items()):
            update_expr += f", #{i}k = :{i}v"
            expr_names[f"#{i}k"] = k
            expr_values[f":{i}v"] = _floats_to_decimal(v)

    ddb.Table(TABLE).update_item(
        Key={"audit_id": audit_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )


def _floats_to_decimal(obj):
    """DynamoDB can't store float — convert recursively."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimal(v) for v in obj]
    return obj


# ── main handler ───────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    batch_item_failures = []

    for record in event["Records"]:
        message   = json.loads(record["body"])
        audit_id  = message["audit_id"]
        s3_key    = message.get("s3_key", "")
        lang      = message.get("lang", "hi")
        source    = message.get("source", "web")

        print(f"[{audit_id}] Starting audit | source={source} | lang={lang}")

        try:
            run_audit(audit_id, s3_key, lang, source, message)
        except Exception as e:
            print(f"[{audit_id}] FATAL: {e}")
            traceback.print_exc()
            # Mark as failed in DynamoDB
            try:
                _update_status(audit_id, "failed", {"error_message": str(e)[:500]})
            except Exception:
                pass
            # Return to SQS for retry (up to maxReceiveCount)
            batch_item_failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": batch_item_failures}


def run_audit(audit_id: str, s3_key: str, lang: str, source: str, message: dict):
    """Run the full audit pipeline."""

    # ── Step 1: Parse quote image ──────────────────────────────────────────────
    print(f"[{audit_id}] Step 1: parse_quote")
    _update_status(audit_id, "parsing")

    extracted = parse_quote(s3_key)
    print(f"[{audit_id}] Extracted: {json.dumps(extracted)}")

    _update_status(audit_id, "checking", {"extracted": extracted})

    # ── Step 2: Check ALMM panel DCR status ───────────────────────────────────
    print(f"[{audit_id}] Step 2: check_almm")
    almm_result = check_almm(
        brand=extracted.get("brand") or "",
        model=extracted.get("model"),
        system_kw=extracted.get("system_kw") or 3.0,
    )
    print(f"[{audit_id}] ALMM: {almm_result['dcr_status']}")

    # ── Step 3: Check vendor empanelment ──────────────────────────────────────
    print(f"[{audit_id}] Step 3: check_vendor")
    vendor_result = check_vendor(
        vendor_name=extracted.get("vendor_name") or "",
        state="HP",
    )
    print(f"[{audit_id}] Vendor: {vendor_result['status']}")

    # ── Step 4: Calculate subsidy ─────────────────────────────────────────────
    print(f"[{audit_id}] Step 4: calc_subsidy")
    subsidy_result = calc_subsidy(
        system_kw=extracted.get("system_kw") or 3.0,
        state="HP",
    )

    # ── Step 5: Calculate generation (NASA POWER) ─────────────────────────────
    print(f"[{audit_id}] Step 5: calc_generation")
    gen_result = calc_generation(system_kw=extracted.get("system_kw") or 3.0)

    # ── Step 6: Check price ───────────────────────────────────────────────────
    print(f"[{audit_id}] Step 6: check_price")
    price_result = check_price(
        quoted_price=extracted.get("quoted_price") or 0,
        system_kw=extracted.get("system_kw") or 3.0,
        state="HP",
    )

    # ── Step 7: Build verdict ─────────────────────────────────────────────────
    print(f"[{audit_id}] Step 7: build_verdict")
    verdict = build_verdict(
        almm_result=almm_result,
        vendor_result=vendor_result,
        price_result=price_result,
        subsidy_result=subsidy_result,
        gen_result=gen_result,
        extracted=extracted,
        lang=lang,
    )
    print(f"[{audit_id}] Verdict: {verdict['verdict']}")

    # ── Step 8: Polly voice note ──────────────────────────────────────────────
    print(f"[{audit_id}] Step 8: generate_voice_note")
    try:
        audio_url = generate_voice_note(verdict, audit_id, lang)
        verdict["audio_url"] = audio_url
    except Exception as e:
        print(f"[{audit_id}] Polly failed (non-fatal): {e}")
        verdict["audio_url"] = None

    # ── Step 9: Save final result ─────────────────────────────────────────────
    print(f"[{audit_id}] Step 9: saving result")
    _update_status(audit_id, "complete", {
        "extracted":      extracted,
        "almm_result":    almm_result,
        "vendor_result":  vendor_result,
        "price_result":   price_result,
        "subsidy_result": subsidy_result,
        "gen_result":     gen_result,
        "verdict":        verdict,
    })

    print(f"[{audit_id}] ✅ Complete — {verdict['verdict']}")
