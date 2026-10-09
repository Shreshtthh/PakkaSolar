"""
backend/status_handler/lambda_function.py
------------------------------------------
GET /status/{audit_id} → returns audit state from DynamoDB.
Frontend polls this every 2s.
"""
import json
import os

import boto3
from boto3.dynamodb.types import TypeDeserializer

ddb   = boto3.resource("dynamodb")
TABLE = os.environ["AUDITS_TABLE"]


def _headers():
    return {
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET,OPTIONS",
        "Content-Type": "application/json",
    }


def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": _headers(), "body": ""}

    audit_id = (event.get("pathParameters") or {}).get("audit_id", "").strip()

    if not audit_id:
        return {
            "statusCode": 400,
            "headers": _headers(),
            "body": json.dumps({"error": "audit_id required"}),
        }

    try:
        resp = ddb.Table(TABLE).get_item(Key={"audit_id": audit_id})
    except Exception as e:
        print(f"DynamoDB error: {e}")
        return {
            "statusCode": 500,
            "headers": _headers(),
            "body": json.dumps({"error": "Database error"}),
        }

    item = resp.get("Item")
    if not item:
        return {
            "statusCode": 404,
            "headers": _headers(),
            "body": json.dumps({"error": "Audit not found"}),
        }

    # Convert Decimal → float for JSON serialisation
    item = _decimal_to_float(item)

    # Don't expose the raw S3 key or internal fields
    item.pop("s3_key", None)
    item.pop("ttl", None)

    return {
        "statusCode": 200,
        "headers": _headers(),
        "body": json.dumps(item),
    }


def _decimal_to_float(obj):
    """Recursively convert Decimal objects to float (DynamoDB returns Decimal)."""
    from decimal import Decimal
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(v) for v in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    return obj
