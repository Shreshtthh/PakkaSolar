"""
tests/test_suite.py
-------------------
Full test suite for PakkaSolar backend.

Run from /root/EnvironmentHacks/backend/:
    pip install pytest moto boto3 pydantic
    pytest tests/ -v

Groups:
  TestPureLogic    — no AWS, no mocking, pure Python
  TestAWSTools     — moto-backed DynamoDB/S3 tests
  TestLambdaHandlers — full Lambda handler tests with moto
  TestImports      — verify all modules import cleanly (catches missing deps)
"""
import base64
import importlib
import json
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws


# ══════════════════════════════════════════════════════════════════════════════
# 1. IMPORT SMOKE TESTS
#    These run before anything else. If they fail, something is missing.
# ══════════════════════════════════════════════════════════════════════════════

class TestImports:
    def test_calc_subsidy_imports(self):
        from tools.calc_subsidy import calc_subsidy
        assert callable(calc_subsidy)

    def test_check_price_imports(self):
        from tools.check_price import check_price
        assert callable(check_price)

    def test_build_verdict_imports(self):
        from tools.build_verdict import build_verdict
        assert callable(build_verdict)

    def test_calc_generation_imports(self):
        from tools.calc_generation import calc_generation, _load_ghi
        assert callable(calc_generation)

    def test_parse_quote_imports(self):
        from tools.parse_quote import parse_quote, QuoteExtraction
        assert callable(parse_quote)

    def test_check_almm_imports(self):
        from tools.check_almm import check_almm, _normalize
        assert callable(check_almm)

    def test_check_vendor_imports(self):
        from tools.check_vendor import check_vendor
        assert callable(check_vendor)

    def test_polly_imports(self):
        from polly import generate_voice_note
        assert callable(generate_voice_note)

    def test_webhook_handler_imports(self):
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "webhook_lf_import_check",
            Path(__file__).parent.parent / "webhook_handler" / "lambda_function.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "lambda_handler")

    def test_status_handler_imports(self):
        # status_handler also exports lambda_handler — check via path
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "status_lambda",
            Path(__file__).parent.parent / "status_handler" / "lambda_function.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "lambda_handler")


# ══════════════════════════════════════════════════════════════════════════════
# 2. PURE LOGIC TESTS (no AWS, no mocking)
# ══════════════════════════════════════════════════════════════════════════════

class TestCalcSubsidy:
    """calc_subsidy is pure Python math — no mocking needed."""

    def setup_method(self):
        from tools.calc_subsidy import calc_subsidy
        self.calc = calc_subsidy

    def test_1kw_general(self):
        r = self.calc(1.0, state="MH")
        assert r["subsidy_amount"] == 30_000
        assert r["eligible"] is True

    def test_2kw_general(self):
        r = self.calc(2.0, state="MH")
        assert r["subsidy_amount"] == 60_000

    def test_3kw_general(self):
        r = self.calc(3.0, state="MH")
        # base = 60000 + 18000 = 78000, cap general = 78000
        assert r["subsidy_amount"] == 78_000

    def test_3kw_hp_special_category(self):
        r = self.calc(3.0, state="HP")
        # cap_special = 78000 * 1.10 = 85800
        assert r["subsidy_amount"] == 85_800

    def test_hp_is_special_category(self):
        hp = self.calc(3.0, "HP")
        gen = self.calc(3.0, "MH")
        assert hp["subsidy_amount"] > gen["subsidy_amount"]

    def test_cap_not_exceeded_for_large_system(self):
        # 10kW system should still cap at 85800 for HP
        r = self.calc(10.0, state="HP")
        assert r["subsidy_amount"] == 85_800

    def test_breakdown_string_present(self):
        r = self.calc(3.0, "HP")
        assert isinstance(r["breakdown"], str)
        assert len(r["breakdown"]) > 0


class TestCheckPrice:
    """check_price is pure logic — no mocking needed."""

    def setup_method(self):
        from tools.check_price import check_price
        self.check = check_price

    def test_fair_price_passes(self):
        # ₹60,000/kW × 3kW = ₹1,80,000 — within benchmark
        r = self.check(quoted_price=180_000, system_kw=3.0, state="HP")
        assert r["status"] == "PASS"
        assert r["price_per_kw"] == 60_000

    def test_too_low_is_amber(self):
        # ₹30,000/kW × 3kW = ₹90,000 — suspiciously cheap (< 80% of low benchmark)
        r = self.check(quoted_price=90_000, system_kw=3.0, state="HP")
        assert r["status"] == "AMBER"
        assert "low" in r["detail"].lower() or "unusual" in r["detail"].lower()

    def test_too_high_is_amber(self):
        # ₹1,00,000/kW × 3kW = ₹3,00,000 — way over benchmark
        r = self.check(quoted_price=300_000, system_kw=3.0, state="HP")
        assert r["status"] == "AMBER"

    def test_missing_price_is_uncertain(self):
        r = self.check(quoted_price=0, system_kw=3.0)
        assert r["status"] == "UNCERTAIN"

    def test_price_per_kw_calculated_correctly(self):
        r = self.check(quoted_price=195_000, system_kw=3.0)
        assert r["price_per_kw"] == 65_000


class TestBuildVerdict:
    """build_verdict is pure assembly logic."""

    def setup_method(self):
        from tools.build_verdict import build_verdict
        self.build = build_verdict

    def _make_inputs(self, dcr="PASS", vendor="PASS", price="PASS"):
        almm   = {"dcr_status": dcr,    "detail": "test", "matched_brand": "Waaree"}
        vend   = {"status": vendor,     "detail": "test", "matched": "Sharma Solar"}
        pr     = {"status": price,      "detail": "test", "price_per_kw": 60000}
        sub    = {"subsidy_amount": 85800, "eligible": True, "breakdown": "test"}
        gen    = {"annual_kwh": 4380, "co2_avoided_kg_yr": 3136, "co2_avoided_tonnes_yr": 3.1}
        ext    = {"system_kw": 3.0, "brand": "Waaree", "vendor_name": "Sharma Solar",
                  "quoted_price": 180000}
        return almm, vend, pr, sub, gen, ext

    def test_all_pass_is_green(self):
        almm, vend, pr, sub, gen, ext = self._make_inputs("PASS", "PASS", "PASS")
        r = self.build(almm, vend, pr, sub, gen, ext, lang="en")
        assert r["verdict"] == "GREEN"

    def test_fail_panel_is_red(self):
        almm, vend, pr, sub, gen, ext = self._make_inputs("FAIL", "PASS", "PASS")
        r = self.build(almm, vend, pr, sub, gen, ext)
        assert r["verdict"] == "RED"

    def test_fail_vendor_is_red(self):
        almm, vend, pr, sub, gen, ext = self._make_inputs("PASS", "FAIL", "PASS")
        r = self.build(almm, vend, pr, sub, gen, ext)
        assert r["verdict"] == "RED"

    def test_uncertain_panel_is_amber(self):
        almm, vend, pr, sub, gen, ext = self._make_inputs("UNCERTAIN", "PASS", "PASS")
        r = self.build(almm, vend, pr, sub, gen, ext)
        assert r["verdict"] == "AMBER"

    def test_not_found_vendor_is_amber(self):
        almm, vend, pr, sub, gen, ext = self._make_inputs("PASS", "NOT_FOUND", "PASS")
        r = self.build(almm, vend, pr, sub, gen, ext)
        assert r["verdict"] == "AMBER"

    def test_red_verdict_has_vendor_message(self):
        almm, vend, pr, sub, gen, ext = self._make_inputs("FAIL", "PASS", "PASS")
        r = self.build(almm, vend, pr, sub, gen, ext, lang="hi")
        assert r["vendor_message"] is not None
        assert len(r["vendor_message"]) > 20

    def test_green_has_no_vendor_message(self):
        almm, vend, pr, sub, gen, ext = self._make_inputs("PASS", "PASS", "PASS")
        r = self.build(almm, vend, pr, sub, gen, ext)
        assert r["vendor_message"] is None

    def test_verdict_has_required_keys(self):
        almm, vend, pr, sub, gen, ext = self._make_inputs()
        r = self.build(almm, vend, pr, sub, gen, ext)
        for key in ["verdict", "summary", "summary_hi", "summary_en", "checks", "subsidy", "generation"]:
            assert key in r, f"Missing key: {key}"

    def test_hindi_summary_present_for_all_verdicts(self):
        for dcr, expected in [("PASS", "GREEN"), ("FAIL", "RED"), ("UNCERTAIN", "AMBER")]:
            almm, vend, pr, sub, gen, ext = self._make_inputs(dcr)
            r = self.build(almm, vend, pr, sub, gen, ext, lang="hi")
            assert r["summary_hi"], f"No Hindi summary for {expected}"


class TestParseQuoteValidators:
    """Test Pydantic validators without touching Bedrock."""

    def test_warranty_string_coerced(self):
        from tools.parse_quote import QuoteExtraction
        q = QuoteExtraction(system_kw=3.0, warranty_years="25 Years")
        assert q.warranty_years == 25

    def test_warranty_none_stays_none(self):
        from tools.parse_quote import QuoteExtraction
        q = QuoteExtraction(system_kw=3.0, warranty_years=None)
        assert q.warranty_years is None

    def test_price_string_coerced(self):
        from tools.parse_quote import QuoteExtraction
        q = QuoteExtraction(system_kw=3.0, quoted_price="₹1,85,000")
        assert q.quoted_price == 185_000

    def test_price_with_commas_coerced(self):
        from tools.parse_quote import QuoteExtraction
        q = QuoteExtraction(system_kw=3.0, quoted_price="1,90,000")
        assert q.quoted_price == 190_000

    def test_system_kw_none_defaults(self):
        from tools.parse_quote import QuoteExtraction
        q = QuoteExtraction(system_kw=None)
        assert q.system_kw == 3.0

    def test_mock_mode_returns_dict(self):
        """MOCK_MODE=true must return a complete dict without calling Bedrock."""
        from tools.parse_quote import parse_quote
        result = parse_quote("uploads/test.jpg")
        assert isinstance(result, dict)
        assert "system_kw" in result
        assert "brand" in result
        assert result["system_kw"] == 3.0

    def test_warranty_text_with_unit(self):
        from tools.parse_quote import QuoteExtraction
        q = QuoteExtraction(system_kw=3.0, warranty_years="25-year performance warranty")
        assert q.warranty_years == 25


# ══════════════════════════════════════════════════════════════════════════════
# 3. AWS TOOL TESTS (moto-backed)
# ══════════════════════════════════════════════════════════════════════════════

@mock_aws
class TestCalcGeneration:
    """Tests calc_generation, especially the ANN key regression."""

    def _setup_s3_with_data(self, monthly_data: dict):
        """Create the mocked S3 bucket and upload NASA POWER JSON."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="pakkasolar-media-test")
        payload = {
            "properties": {
                "parameter": {
                    "ALLSKY_SFC_SW_DWN": monthly_data
                }
            }
        }
        s3.put_object(
            Bucket="pakkasolar-media-test",
            Key="nasa_power/hamirpur.json",
            Body=json.dumps(payload),
        )

    def test_basic_generation(self):
        from tools.calc_generation import calc_generation
        # 12 months of 5.0 kWh/m²/day → annual = 5*365 = 1825, × 3kW × 0.8 = 4380
        monthly = {f"{i:02d}": 5.0 for i in range(1, 13)}
        self._setup_s3_with_data(monthly)
        r = calc_generation(system_kw=3.0)
        assert r["annual_kwh"] == pytest.approx(4380, abs=10)

    def test_ann_key_excluded(self):
        """REGRESSION: ANN key must NOT affect average calculation."""
        from tools.calc_generation import _load_ghi
        monthly = {f"{i:02d}": 5.0 for i in range(1, 13)}
        monthly["ANN"] = 5.0   # ANN key present — should be ignored
        self._setup_s3_with_data(monthly)

        ghi_with_ann    = _load_ghi()

        # Without ANN in data
        monthly_clean = {f"{i:02d}": 5.0 for i in range(1, 13)}
        self._setup_s3_with_data(monthly_clean)
        ghi_without_ann = _load_ghi()

        assert ghi_with_ann == pytest.approx(ghi_without_ann, rel=0.001), \
            "ANN key is contaminating the GHI average!"

    def test_ann_key_with_different_value(self):
        """ANN with different value than monthly avg must not distort result."""
        from tools.calc_generation import _load_ghi
        # 12 months averaging 4.5, ANN says 99.0 (wrong)
        monthly = {f"{i:02d}": 4.5 for i in range(1, 13)}
        monthly["ANN"] = 99.0
        self._setup_s3_with_data(monthly)
        ghi = _load_ghi()
        # Should be 4.5 * 365 = 1642.5, NOT (4.5*12 + 99)/13 * 365
        assert ghi == pytest.approx(4.5 * 365, rel=0.01), \
            f"ANN key distorted GHI: got {ghi:.1f}, expected {4.5*365:.1f}"

    def test_fallback_when_s3_unavailable(self):
        """Must return fallback GHI when S3 has no cache."""
        from tools.calc_generation import _load_ghi, HAMIRPUR_GHI_FALLBACK
        # Don't set up S3 data → should fall back
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="pakkasolar-media-test")
        ghi = _load_ghi()
        assert ghi == pytest.approx(HAMIRPUR_GHI_FALLBACK * 365, rel=0.001)

    def test_co2_and_savings_present(self):
        from tools.calc_generation import calc_generation
        monthly = {f"{i:02d}": 5.0 for i in range(1, 13)}
        self._setup_s3_with_data(monthly)
        r = calc_generation(3.0)
        assert r["co2_avoided_kg_yr"] > 0
        assert r["annual_savings_inr"] > 0
        assert r["ghi_source"] == "NASA POWER (AWS Open Data Registry)"


@mock_aws
class TestCheckAlmm:
    """Tests ALMM DynamoDB lookup with different brand matching strategies."""

    BRANDS = [
        ("waaree_energies_limited",        "ws-540m",      "Waaree Energies Limited",    "ws-540m"),
        ("adani_solar",                    "ast-540",      "Adani Solar",                "ast-540"),
        ("vikram_solar_pvt_ltd",           "eldora-540",   "Vikram Solar Pvt. Ltd.",     "eldora-540"),
        ("goldi_solar_pvt_limited",        "g2x-530",      "Goldi Solar Pvt. Limited",   "g2x-530"),
    ]

    def _setup_dynamo(self):
        """Create and populate the ALMM DynamoDB table."""
        ddb = boto3.resource("dynamodb", region_name="ap-south-1")
        table = ddb.create_table(
            TableName="pakkasolar-almm-panels",
            KeySchema=[
                {"AttributeName": "brand_normalized", "KeyType": "HASH"},
                {"AttributeName": "model_prefix",     "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "brand_normalized", "AttributeType": "S"},
                {"AttributeName": "model_prefix",     "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        for brand_norm, model_prefix, brand_display, model_raw in self.BRANDS:
            table.put_item(Item={
                "brand_normalized": brand_norm,
                "model_prefix":     model_prefix,
                "brand_display":    brand_display,
                "model_raw":        model_raw,
                "dcr_certified":    True,
                "cell_type":        "Mono c-Si PERC Module",
                "list_version":     "ALMM List-I v2026",
                "watt_range_min":   Decimal("530"),
                "watt_range_max":   Decimal("560"),
            })
        return table

    def test_exact_brand_match(self):
        """'Waaree Energies Limited' → exact match → PASS."""
        import importlib
        import tools.check_almm as ca
        self._setup_dynamo()
        ca._ALL_BRANDS.clear()   # reset cache
        r = ca.check_almm("Waaree Energies Limited", "WS-540M", 3.0)
        assert r["dcr_status"] == "PASS"
        assert "Waaree" in r["matched_brand"]

    def test_prefix_brand_match(self):
        """'Waaree' (partial) should fuzzy-match 'waaree_energies_limited'."""
        import tools.check_almm as ca
        self._setup_dynamo()
        ca._ALL_BRANDS.clear()
        r = ca.check_almm("Waaree", "WS-540", 3.0)
        assert r["dcr_status"] in ("PASS", "UNCERTAIN")  # uncertain is ok too

    def test_unknown_brand_returns_uncertain(self):
        """Completely unknown brand → UNCERTAIN, never FAIL."""
        import tools.check_almm as ca
        self._setup_dynamo()
        ca._ALL_BRANDS.clear()
        r = ca.check_almm("XYZ Fake Solar Ltd", None, 3.0)
        assert r["dcr_status"] == "UNCERTAIN"
        assert r["matched_brand"] is None

    def test_empty_brand_returns_uncertain(self):
        import tools.check_almm as ca
        r = ca.check_almm("", None, 3.0)
        assert r["dcr_status"] == "UNCERTAIN"

    def test_normalize_strips_ms_prefix(self):
        from tools.check_almm import _normalize
        assert _normalize("M/s Waaree Energies") == "waaree_energies"
        assert _normalize("M/s. Adani Solar") == "adani_solar"


@mock_aws
class TestCheckVendor:
    """Tests vendor empanelment lookup."""

    def _setup_dynamo(self):
        ddb = boto3.resource("dynamodb", region_name="ap-south-1")
        table = ddb.create_table(
            TableName="pakkasolar-vendors",
            KeySchema=[
                {"AttributeName": "state_code",             "KeyType": "HASH"},
                {"AttributeName": "vendor_name_normalized", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "state_code",             "AttributeType": "S"},
                {"AttributeName": "vendor_name_normalized", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        # Good vendor
        table.put_item(Item={
            "state_code":             "HP",
            "vendor_name_normalized": "sharma",
            "vendor_display":         "Sharma Solar, Hamirpur",
            "empanelled":             True,
            "discom":                 "HPSEBL",
        })
        # Bad vendor (not empanelled)
        table.put_item(Item={
            "state_code":             "HP",
            "vendor_name_normalized": "cheapo",
            "vendor_display":         "Cheapo Solar Traders",
            "empanelled":             False,
            "discom":                 "HPSEBL",
        })
        return table

    def test_empanelled_vendor_passes(self):
        import tools.check_vendor as cv
        self._setup_dynamo()
        cv._VENDOR_CACHE.clear()
        r = cv.check_vendor("Sharma Solar", state="HP")
        assert r["status"] == "PASS"
        assert "Sharma" in r["matched"]

    def test_not_empanelled_vendor_fails(self):
        import tools.check_vendor as cv
        self._setup_dynamo()
        cv._VENDOR_CACHE.clear()
        r = cv.check_vendor("Cheapo Solar", state="HP")
        assert r["status"] == "FAIL"

    def test_unknown_vendor_not_found(self):
        import tools.check_vendor as cv
        self._setup_dynamo()
        cv._VENDOR_CACHE.clear()
        r = cv.check_vendor("Random Unknown Co", state="HP")
        assert r["status"] == "NOT_FOUND"

    def test_empty_vendor_name(self):
        import tools.check_vendor as cv
        r = cv.check_vendor("", state="HP")
        assert r["status"] == "NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# 4. LAMBDA HANDLER TESTS
# ══════════════════════════════════════════════════════════════════════════════

@mock_aws
class TestWebhookHandler:
    """Tests the webhook_handler Lambda."""

    BUCKET = "pakkasolar-media-test"
    REGION = "ap-south-1"

    def _get_webhook_handler(self):
        """Load webhook_handler/lambda_function.py explicitly to avoid
        namespace collision with audit_worker/lambda_function.py."""
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "webhook_lf",
            Path(__file__).parent.parent / "webhook_handler" / "lambda_function.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _setup(self):
        """Create S3 bucket, SQS queue, and DynamoDB table."""
        s3 = boto3.client("s3", region_name=self.REGION)
        s3.create_bucket(
            Bucket=self.BUCKET,
            CreateBucketConfiguration={"LocationConstraint": self.REGION},
        )

        sqs = boto3.client("sqs", region_name=self.REGION)
        q   = sqs.create_queue(QueueName="pakkasolar-audit-queue")
        os.environ["AUDIT_QUEUE_URL"] = q["QueueUrl"]

        ddb = boto3.resource("dynamodb", region_name=self.REGION)
        ddb.create_table(
            TableName="pakkasolar-audits",
            KeySchema=[{"AttributeName": "audit_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "audit_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

    def _make_upload_event(self, image_b64: str, lang: str = "hi") -> dict:
        return {
            "httpMethod": "POST",
            "path": "/audit",
            "body": json.dumps({"image_b64": image_b64, "lang": lang}),
            "headers": {"Content-Type": "application/json"},
            "pathParameters": None,
            "queryStringParameters": None,
        }

    def test_valid_upload_returns_202(self):
        self._setup()
        lf = self._get_webhook_handler()

        # A minimal fake JPEG (just needs to be >1000 bytes)
        fake_jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 2000
        img_b64  = base64.b64encode(fake_jpg).decode()

        resp = lf.lambda_handler(self._make_upload_event(img_b64), {})
        assert resp["statusCode"] == 202
        body = json.loads(resp["body"])
        assert "audit_id" in body
        assert body["status"] == "pending"

    def test_missing_image_returns_400(self):
        self._setup()
        lf = self._get_webhook_handler()

        event = {
            "httpMethod": "POST",
            "path": "/audit",
            "body": json.dumps({"lang": "hi"}),
            "pathParameters": None,
            "queryStringParameters": None,
        }
        resp = lf.lambda_handler(event, {})
        assert resp["statusCode"] == 400

    def test_cors_headers_present(self):
        self._setup()
        lf = self._get_webhook_handler()

        fake_jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 2000
        img_b64  = base64.b64encode(fake_jpg).decode()
        resp = lf.lambda_handler(self._make_upload_event(img_b64), {})
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_options_preflight_returns_200(self):
        self._setup()
        lf = self._get_webhook_handler()

        event = {"httpMethod": "OPTIONS", "path": "/audit",
                 "body": None, "pathParameters": None, "queryStringParameters": None}
        resp = lf.lambda_handler(event, {})
        assert resp["statusCode"] == 200

    def test_wa_verify_valid_token(self):
        self._setup()
        lf = self._get_webhook_handler()

        event = {
            "httpMethod": "GET",
            "path": "/webhook/wa",
            "body": None,
            "pathParameters": None,
            "queryStringParameters": {
                "hub.mode":         "subscribe",
                "hub.verify_token": "pakkasolar_verify_2026",
                "hub.challenge":    "abc123",
            },
        }
        resp = lf.lambda_handler(event, {})
        assert resp["statusCode"] == 200
        assert resp["body"] == "abc123"

    def test_wa_verify_wrong_token(self):
        self._setup()
        lf = self._get_webhook_handler()

        event = {
            "httpMethod": "GET",
            "path": "/webhook/wa",
            "body": None,
            "pathParameters": None,
            "queryStringParameters": {
                "hub.mode":         "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge":    "abc123",
            },
        }
        resp = lf.lambda_handler(event, {})
        assert resp["statusCode"] == 403

    def test_upload_creates_dynamo_record(self):
        self._setup()
        lf = self._get_webhook_handler()

        fake_jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 2000
        img_b64  = base64.b64encode(fake_jpg).decode()
        resp     = lf.lambda_handler(self._make_upload_event(img_b64), {})
        audit_id = json.loads(resp["body"])["audit_id"]

        ddb  = boto3.resource("dynamodb", region_name="ap-south-1")
        item = ddb.Table("pakkasolar-audits").get_item(Key={"audit_id": audit_id}).get("Item")
        assert item is not None
        assert item["status"] == "pending"
        assert item["lang"] == "hi"

    def test_upload_sends_sqs_message(self):
        self._setup()
        lf = self._get_webhook_handler()

        fake_jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 2000
        img_b64  = base64.b64encode(fake_jpg).decode()
        lf.lambda_handler(self._make_upload_event(img_b64), {})

        sqs   = boto3.client("sqs", region_name="ap-south-1")
        msgs  = sqs.receive_message(QueueUrl=os.environ["AUDIT_QUEUE_URL"])
        assert "Messages" in msgs
        body  = json.loads(msgs["Messages"][0]["Body"])
        assert "audit_id" in body
        assert body["lang"] == "hi"


@mock_aws
class TestStatusHandler:
    """Tests the status_handler Lambda."""

    def _setup(self):
        ddb = boto3.resource("dynamodb", region_name="ap-south-1")
        ddb.create_table(
            TableName="pakkasolar-audits",
            KeySchema=[{"AttributeName": "audit_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "audit_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        return ddb

    def _make_event(self, audit_id: str) -> dict:
        return {
            "httpMethod": "GET",
            "path": f"/status/{audit_id}",
            "pathParameters": {"audit_id": audit_id},
            "queryStringParameters": None,
            "body": None,
        }

    def test_returns_pending_status(self):
        ddb = self._setup()
        ddb.Table("pakkasolar-audits").put_item(Item={
            "audit_id": "test001",
            "status":   "pending",
            "lang":     "hi",
        })

        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "status_lf",
            Path(__file__).parent.parent / "status_handler" / "lambda_function.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        resp = mod.lambda_handler(self._make_event("test001"), {})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["status"] == "pending"
        assert "s3_key" not in body   # internal field should be stripped
        assert "ttl" not in body

    def test_returns_404_for_missing_id(self):
        self._setup()

        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "status_lf2",
            Path(__file__).parent.parent / "status_handler" / "lambda_function.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        resp = mod.lambda_handler(self._make_event("doesnotexist"), {})
        assert resp["statusCode"] == 404

    def test_decimals_serialised_to_float(self):
        """DynamoDB Decimals must not crash JSON serialisation."""
        ddb = self._setup()
        ddb.Table("pakkasolar-audits").put_item(Item={
            "audit_id":       "test002",
            "status":         "complete",
            "watt_range_min": Decimal("540"),
        })

        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "status_lf3",
            Path(__file__).parent.parent / "status_handler" / "lambda_function.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        resp = mod.lambda_handler(self._make_event("test002"), {})
        assert resp["statusCode"] == 200
        # Must not raise json.JSONDecodeError
        body = json.loads(resp["body"])
        assert body["watt_range_min"] == 540.0
