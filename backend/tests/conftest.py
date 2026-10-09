"""
tests/conftest.py
-----------------
Sets up environment variables and sys.path BEFORE any Lambda module is imported.
Must be loaded first — pytest does this automatically via conftest.py.
"""
import os
import sys
from pathlib import Path

# ── Dummy AWS credentials (required by moto — prevents NoRegionError) ─────────
os.environ.update({
    "AWS_DEFAULT_REGION":    "ap-south-1",
    "AWS_ACCESS_KEY_ID":     "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN":    "testing",
    "AWS_SESSION_TOKEN":     "testing",
})

# ── App environment variables (mirror env.local.json) ─────────────────────────
os.environ.update({
    "MEDIA_BUCKET":    "pakkasolar-media-test",
    "ALMM_TABLE":      "pakkasolar-almm-panels",
    "VENDORS_TABLE":   "pakkasolar-vendors",
    "AUDITS_TABLE":    "pakkasolar-audits",
    "CONFIG_TABLE":    "pakkasolar-config",
    "AUDIT_QUEUE_URL": "https://sqs.ap-south-1.amazonaws.com/123456789012/pakkasolar-audit-queue",
    "BEDROCK_REGION":  "us-east-1",
    "WA_VERIFY_TOKEN": "pakkasolar_verify_2026",
    "MOCK_MODE":       "true",
})

# ── sys.path: add each Lambda package directory ───────────────────────────────
# ROOT is the backend/ directory (parent of tests/).
# Each Lambda lives at ROOT/<subdir>/lambda_function.py.
# Do NOT add "backend" again — we are already inside backend/.
ROOT = Path(__file__).parent.parent
for subdir in ["webhook_handler", "status_handler", "audit_worker"]:
    p = str(ROOT / subdir)
    if p not in sys.path:
        sys.path.insert(0, p)
