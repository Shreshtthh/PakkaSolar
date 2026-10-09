"""
backend/webhook_handler/lambda_function.py
------------------------------------------
Receives image upload → S3 → SQS → returns 202.
Also handles WhatsApp webhook verification challenge.
"""
import base64
import json
import os
import uuid
from datetime import datetime, timezone

import boto3

# ── clients (re-used across warm invocations) ─────────────────────────────────
s3 = boto3.client("s3")
sqs = boto3.client("sqs")
ddb = boto3.resource("dynamodb")

BUCKET    = os.environ["MEDIA_BUCKET"]
QUEUE_URL = os.environ["AUDIT_QUEUE_URL"]
TABLE     = os.environ["AUDITS_TABLE"]
WA_TOKEN  = os.environ.get("WA_VERIFY_TOKEN", "pakkasolar_verify_2026")


def _headers():
    return {
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Content-Type": "application/json",
    }


def ok(body: dict, status: int = 200):
    return {"statusCode": status, "headers": _headers(), "body": json.dumps(body)}


def err(msg: str, status: int = 400):
    return {"statusCode": status, "headers": _headers(), "body": json.dumps({"error": msg})}


# ── router ────────────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    method = event.get("httpMethod", "")
    path   = event.get("path", "")

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": _headers(), "body": ""}

    if path.startswith("/webhook/wa"):
        if method == "GET":
            return _wa_verify(event)
        if method == "POST":
            return _wa_message(event)

    if path == "/audit" and method == "POST":
        return _handle_upload(event)

    return err("Not found", 404)


# ── web upload ─────────────────────────────────────────────────────────────────

def _handle_upload(event):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return err("Invalid JSON body")

    image_b64 = body.get("image_b64", "").strip()
    lang      = body.get("lang", "hi")
    source    = body.get("source", "web")

    if not image_b64:
        return err("image_b64 is required")

    # Decode image
    try:
        img_bytes = base64.b64decode(image_b64)
    except Exception:
        return err("image_b64 is not valid base64")

    if len(img_bytes) < 1000:
        return err("Image too small — did the upload complete?")

    audit_id = uuid.uuid4().hex[:10]
    s3_key   = f"uploads/{audit_id}.jpg"
    now      = datetime.now(timezone.utc).isoformat()
    ttl      = int(datetime.now(timezone.utc).timestamp()) + 86400  # expire in 24h

    # Save image to S3
    try:
        s3.put_object(
            Bucket=BUCKET,
            Key=s3_key,
            Body=img_bytes,
            ContentType="image/jpeg",
        )
    except Exception as e:
        print(f"S3 upload error: {e}")
        return err("Failed to store image", 500)

    # Create pending audit record
    try:
        ddb.Table(TABLE).put_item(Item={
            "audit_id":   audit_id,
            "status":     "pending",
            "source":     source,
            "lang":       lang,
            "s3_key":     s3_key,
            "created_at": now,
            "ttl":        ttl,
        })
    except Exception as e:
        print(f"DynamoDB put error: {e}")
        return err("Failed to create audit record", 500)

    # Enqueue for processing
    try:
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps({
                "audit_id": audit_id,
                "s3_key":   s3_key,
                "lang":     lang,
                "source":   source,
            }),
        )
    except Exception as e:
        print(f"SQS error: {e}")
        return err("Failed to enqueue audit", 500)

    print(f"Audit created: {audit_id} | lang={lang} | size={len(img_bytes)} bytes")

    return ok({"audit_id": audit_id, "status": "pending"}, status=202)


# ── WhatsApp webhook ──────────────────────────────────────────────────────────

def _wa_verify(event):
    params    = event.get("queryStringParameters") or {}
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    if mode == "subscribe" and token == WA_TOKEN:
        return {"statusCode": 200, "headers": _headers(), "body": challenge}
    return err("Forbidden", 403)


def _wa_message(event):
    """
    Process incoming WhatsApp image message.
    Acknowledge immediately (WA requires <3s response),
    then enqueue for async processing.
    """
    try:
        body = json.loads(event.get("body") or "{}")
        entry = body.get("entry", [{}])[0]
        change = entry.get("changes", [{}])[0].get("value", {})
        messages = change.get("messages", [])

        for msg in messages:
            msg_type = msg.get("type")
            from_num = msg.get("from", "unknown")

            if msg_type == "image":
                # Download image from WhatsApp media URL via WA Cloud API
                media_id = msg["image"]["id"]
                # We'll fetch the media URL and download in a separate step
                # For the demo, we call _enqueue_wa_image directly
                _enqueue_wa_image(media_id, from_num)

            elif msg_type == "text":
                # Ignore text messages for now
                print(f"Text from {from_num}: {msg['text']['body'][:50]}")

    except Exception as e:
        print(f"WA message processing error: {e}")

    # Always return 200 to WhatsApp
    return {"statusCode": 200, "headers": _headers(), "body": "OK"}


def _enqueue_wa_image(media_id: str, from_num: str):
    """Enqueue a WhatsApp image for processing."""
    audit_id = uuid.uuid4().hex[:10]
    now      = datetime.now(timezone.utc).isoformat()
    ttl      = int(datetime.now(timezone.utc).timestamp()) + 86400

    ddb.Table(TABLE).put_item(Item={
        "audit_id":   audit_id,
        "status":     "pending",
        "source":     "whatsapp",
        "lang":       "hi",
        "wa_from":    from_num,
        "wa_media_id": media_id,
        "created_at": now,
        "ttl":        ttl,
    })

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            "audit_id":    audit_id,
            "source":      "whatsapp",
            "lang":        "hi",
            "wa_from":     from_num,
            "wa_media_id": media_id,
        }),
    )
    print(f"WA audit enqueued: {audit_id} from {from_num}")
