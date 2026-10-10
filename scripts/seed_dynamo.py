"""
seed_dynamo.py
--------------
Seeds DynamoDB tables from CSV files.

Creates tables if they don't exist (useful for local testing with DynamoDB Local).
For real AWS, tables must already exist (created by SAM deploy).

Usage:
    # Seed real AWS (ap-south-1)
    python scripts/seed_dynamo.py --region ap-south-1

    # Dry run (prints what would be inserted, no writes)
    python scripts/seed_dynamo.py --dry-run

    # Seed local DynamoDB (for testing without AWS)
    python scripts/seed_dynamo.py --local

Install deps:
    pip install boto3 pandas
"""

import argparse
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

# ── paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
SEED_DATA_DIR = SCRIPT_DIR / "seed_data"

ALMM_CSV = SEED_DATA_DIR / "almm_panels.csv"
ALMM_FALLBACK_CSV = SEED_DATA_DIR / "almm_panels_fallback.csv"
VENDORS_CSV = SEED_DATA_DIR / "vendors_hp.csv"

# ── table names (must match template.yaml) ────────────────────────────────────
ALMM_TABLE    = "pakkasolar-almm-panels"
VENDORS_TABLE = "pakkasolar-vendors"
CONFIG_TABLE  = "pakkasolar-config"


# ── helpers ────────────────────────────────────────────────────────────────────

def to_decimal(val):
    """Convert float/int/str to Decimal for DynamoDB (it doesn't accept float)."""
    if val is None or val == "" or val == "None":
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def bool_val(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return False


def get_dynamo(args):
    kwargs = {"region_name": args.region}
    if args.local:
        kwargs["endpoint_url"] = "http://localhost:8000"
        kwargs["aws_access_key_id"] = "local"
        kwargs["aws_secret_access_key"] = "local"
    return boto3.resource("dynamodb", **kwargs)


# ── table creation (for local DynamoDB) ───────────────────────────────────────

def create_tables_if_needed(dynamo, args):
    if not args.local:
        # On real AWS, SAM creates the tables. Don't try to create.
        return

    existing = [t.name for t in dynamo.tables.all()]

    if ALMM_TABLE not in existing:
        print(f"Creating table {ALMM_TABLE} (local)...")
        dynamo.create_table(
            TableName=ALMM_TABLE,
            KeySchema=[
                {"AttributeName": "brand_normalized", "KeyType": "HASH"},
                {"AttributeName": "model_prefix", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "brand_normalized", "AttributeType": "S"},
                {"AttributeName": "model_prefix", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

    if VENDORS_TABLE not in existing:
        print(f"Creating table {VENDORS_TABLE} (local)...")
        dynamo.create_table(
            TableName=VENDORS_TABLE,
            KeySchema=[
                {"AttributeName": "state_code", "KeyType": "HASH"},
                {"AttributeName": "vendor_name_normalized", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "state_code", "AttributeType": "S"},
                {"AttributeName": "vendor_name_normalized", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

    if CONFIG_TABLE not in existing:
        print(f"Creating table {CONFIG_TABLE} (local)...")
        dynamo.create_table(
            TableName=CONFIG_TABLE,
            KeySchema=[
                {"AttributeName": "config_key", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "config_key", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

    # Wait for tables to be active
    for name in [ALMM_TABLE, VENDORS_TABLE, CONFIG_TABLE]:
        dynamo.Table(name).wait_until_exists()


# ── seeding functions ──────────────────────────────────────────────────────────

def seed_almm(dynamo, dry_run: bool):
    """Seed almm_panels table from CSV."""
    # Use fallback if main CSV doesn't exist
    csv_path = ALMM_CSV if ALMM_CSV.exists() else ALMM_FALLBACK_CSV
    if not csv_path.exists():
        print(f"ERROR: No ALMM CSV found at {ALMM_CSV} or {ALMM_FALLBACK_CSV}", file=sys.stderr)
        return 0

    print(f"\nSeeding {ALMM_TABLE} from {csv_path.name} ...")
    table = dynamo.Table(ALMM_TABLE)

    count = 0
    errors = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        with table.batch_writer() as batch:
            for row in reader:
                brand_norm = row.get("brand_normalized", "").strip()
                model_prefix = row.get("model_prefix", "").strip()

                if not brand_norm or not model_prefix:
                    continue

                item = {
                    "brand_normalized": brand_norm,
                    "model_prefix": model_prefix,
                    "brand_display": row.get("brand_display", brand_norm).strip(),
                    "model_raw": row.get("model_raw", "").strip(),   # human-readable model name
                    "cell_type": row.get("cell_type", "Unknown").strip(),
                    "dcr_certified": bool_val(row.get("dcr_certified", "true")),
                    "list_name": row.get("list_name", "ALMM List-I (Modules)").strip(),
                    "list_version": row.get("list_version", "v2026").strip(),
                }

                # Add watt range only if parseable
                w_min = to_decimal(row.get("watt_range_min"))
                w_max = to_decimal(row.get("watt_range_max"))
                if w_min is not None:
                    item["watt_range_min"] = w_min
                if w_max is not None:
                    item["watt_range_max"] = w_max

                if dry_run:
                    print(f"  [DRY RUN] Would insert: {brand_norm} / {model_prefix}")
                else:
                    try:
                        batch.put_item(Item=item)
                        count += 1
                    except Exception as e:
                        print(f"  ERROR on {brand_norm}/{model_prefix}: {e}")
                        errors += 1

    if dry_run:
        print(f"  [DRY RUN] Would have inserted rows from {csv_path.name}")
    else:
        print(f"  ✅ Inserted {count} panel records ({errors} errors)")
    return count


def seed_vendors(dynamo, dry_run: bool):
    """Seed vendors table from CSV."""
    if not VENDORS_CSV.exists():
        print(f"ERROR: Vendor CSV not found at {VENDORS_CSV}", file=sys.stderr)
        return 0

    print(f"\nSeeding {VENDORS_TABLE} from {VENDORS_CSV.name} ...")
    table = dynamo.Table(VENDORS_TABLE)

    count = 0
    errors = 0
    with open(VENDORS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        with table.batch_writer() as batch:
            for row in reader:
                state = row.get("state_code", "").strip()
                vendor_norm = row.get("vendor_name_normalized", "").strip()

                if not state or not vendor_norm:
                    continue

                item = {
                    "state_code": state,
                    "vendor_name_normalized": vendor_norm,
                    "vendor_display": row.get("vendor_display", vendor_norm).strip(),
                    "district": row.get("district", "").strip(),
                    "discom": row.get("discom", "").strip(),
                    "empanelled": bool_val(row.get("empanelled", "false")),
                    "last_verified": row.get("last_verified", "2026-10-08").strip(),
                }

                phone = row.get("contact_phone", "").strip()
                if phone:
                    item["contact_phone"] = phone

                if dry_run:
                    print(f"  [DRY RUN] Would insert: {state} / {vendor_norm} (empanelled={item['empanelled']})")
                else:
                    try:
                        batch.put_item(Item=item)
                        count += 1
                    except Exception as e:
                        print(f"  ERROR on {state}/{vendor_norm}: {e}")
                        errors += 1

    if dry_run:
        print(f"  [DRY RUN] Would have inserted rows from {VENDORS_CSV.name}")
    else:
        print(f"  ✅ Inserted {count} vendor records ({errors} errors)")
    return count


def seed_config(dynamo, dry_run: bool):
    """Seed subsidy rates and tariff config."""
    print(f"\nSeeding {CONFIG_TABLE} ...")
    table = dynamo.Table(CONFIG_TABLE)

    configs = [
        {
            "config_key": "subsidy_rates",
            "rate_per_kw_slab1": Decimal("30000"),   # 0-2 kW
            "rate_per_kw_slab2": Decimal("18000"),   # 3rd kW
            "cap_general": Decimal("78000"),
            "cap_special_category": Decimal("85800"),  # HP, JK, NE, Uttarakhand
            "special_category_states": ["HP", "JK", "UK", "MN", "MZ", "NL", "AR", "SK", "TR", "ML", "AS"],
            "source": "pmsuryaghar.gov.in",
            "last_updated": "2026-10-08",
        },
        {
            "config_key": "mnre_benchmark_price",
            # Price per kW in INR (inclusive of panels, inverter, mounting, wiring)
            "general_low_per_kw": Decimal("55000"),
            "general_high_per_kw": Decimal("70000"),
            "special_category_premium": Decimal("1.10"),  # 10% higher acceptable for HP/hill states
            "source": "MNRE benchmark circulars",
            "last_updated": "2026-10-08",
        },
        {
            "config_key": "cea_co2_factor",
            "kg_co2_per_kwh": Decimal("0.716"),
            "source": "CEA Baseline Document FY2023-24",
            "last_updated": "2026-10-08",
        },
        {
            "config_key": "hpsebl_tariff",
            "slab1_units": 125,
            "slab1_rate": Decimal("3.50"),
            "slab2_units": 300,
            "slab2_rate": Decimal("4.80"),
            "slab3_rate": Decimal("6.00"),
            "source": "HPERC tariff order (verify current order)",
            "last_updated": "2026-10-08",
        },
        {
            "config_key": "almm_version",
            "list_i_version": "v2026",
            "list_i_date": "2026-04-01",
            "source": "mnre.gov.in",
            "last_updated": "2026-10-08",
        },
    ]

    for cfg in configs:
        if dry_run:
            print(f"  [DRY RUN] Would insert config: {cfg['config_key']}")
        else:
            try:
                table.put_item(Item=cfg)
                print(f"  ✅ Config: {cfg['config_key']}")
            except Exception as e:
                print(f"  ERROR on {cfg['config_key']}: {e}")


def verify_seeding(dynamo):
    """Quick sanity check after seeding."""
    print("\n── Verification ──────────────────────────────────────")

    # Check ALMM
    almm = dynamo.Table(ALMM_TABLE)
    try:
        resp = almm.query(
            KeyConditionExpression=Key("brand_normalized").eq("waaree_energies"),
            Limit=3
        )
        print(f"  ALMM query (waaree_energies): {len(resp['Items'])} items found")
        for item in resp["Items"]:
            print(f"    → {item['brand_display']} | {item['model_prefix']} | DCR={item['dcr_certified']}")
    except Exception as e:
        print(f"  ERROR querying ALMM: {e}")

    # Check vendors
    vendors = dynamo.Table(VENDORS_TABLE)
    try:
        resp = vendors.query(
            KeyConditionExpression=Key("state_code").eq("HP"),
            Limit=3
        )
        print(f"\n  Vendors (HP): {len(resp['Items'])} items found (showing 3)")
        for item in resp["Items"]:
            print(f"    → {item['vendor_display']} | empanelled={item['empanelled']}")
    except Exception as e:
        print(f"  ERROR querying vendors: {e}")

    print("──────────────────────────────────────────────────────")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seed PakkaSolar DynamoDB tables")
    parser.add_argument("--region", default="ap-south-1", help="AWS region")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted, no writes")
    parser.add_argument("--local", action="store_true", help="Use local DynamoDB (localhost:8000)")
    parser.add_argument("--only", choices=["almm", "vendors", "config"], help="Seed only one table")
    args = parser.parse_args()

    if args.dry_run:
        print("🔍 DRY RUN mode — no writes will happen\n")

    dynamo = get_dynamo(args)

    if args.local:
        print("🏠 Using local DynamoDB at localhost:8000")
        create_tables_if_needed(dynamo, args)
    else:
        print(f"☁️  Using AWS DynamoDB in {args.region}")

    if args.only == "almm" or args.only is None:
        seed_almm(dynamo, args.dry_run)

    if args.only == "vendors" or args.only is None:
        seed_vendors(dynamo, args.dry_run)

    if args.only == "config" or args.only is None:
        seed_config(dynamo, args.dry_run)

    if not args.dry_run:
        verify_seeding(dynamo)

    print("\n✅ Done.")


if __name__ == "__main__":
    main()
