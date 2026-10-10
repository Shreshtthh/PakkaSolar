"""
fetch_nasa_power.py
-------------------
Pre-fetches NASA POWER solar irradiance data for HP districts and caches to S3.

Usage:
    # Fetch and upload to S3
    python scripts/fetch_nasa_power.py --bucket your-bucket-name

    # Fetch and save locally only (no S3)
    python scripts/fetch_nasa_power.py --local-only --out scripts/seed_data/nasa_power/

Install deps:
    pip install requests boto3
"""

import argparse
import json
import time
from pathlib import Path

import requests

# ── HP district coordinates ────────────────────────────────────────────────────
# lat/lon for district headquarters
HP_DISTRICTS = {
    "hamirpur":   {"lat": 31.6862, "lon": 76.5222, "label": "Hamirpur, HP"},
    "shimla":     {"lat": 31.1048, "lon": 77.1734, "label": "Shimla, HP"},
    "dharamsala": {"lat": 32.2190, "lon": 76.3234, "label": "Dharamsala (Kangra), HP"},
    "mandi":      {"lat": 31.7094, "lon": 76.9318, "label": "Mandi, HP"},
    "kullu":      {"lat": 31.9579, "lon": 77.1095, "label": "Kullu, HP"},
    "solan":      {"lat": 30.9045, "lon": 77.0967, "label": "Solan, HP"},
    "una":        {"lat": 31.4685, "lon": 76.2708, "label": "Una, HP"},
    "bilaspur":   {"lat": 31.3312, "lon": 76.7554, "label": "Bilaspur, HP"},
    "chamba":     {"lat": 32.5536, "lon": 76.1261, "label": "Chamba, HP"},
}

# Extra cities for demo diversity
EXTRA_CITIES = {
    "delhi":     {"lat": 28.6139, "lon": 77.2090, "label": "Delhi, DL"},
    "bengaluru": {"lat": 12.9716, "lon": 77.5946, "label": "Bengaluru, KA"},
    "jaipur":    {"lat": 26.9124, "lon": 75.7873, "label": "Jaipur, RJ"},
}

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"


def fetch_ghi(lat: float, lon: float, label: str) -> dict | None:
    """Fetch annual + monthly GHI from NASA POWER API."""
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN",
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "format": "JSON",
    }
    print(f"  Fetching {label} ({lat}, {lon})...", end=" ")
    try:
        resp = requests.get(NASA_POWER_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        monthly = data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
        # NASA POWER returns months 1-12 + ANN (annual) as keys
        annual = monthly.pop("ANN", None)

        result = {
            "label": label,
            "lat": lat,
            "lon": lon,
            "monthly_ghi_kwh_m2_day": monthly,   # Jan-Dec
            "annual_ghi_kwh_m2_yr": annual * 365 if annual else sum(monthly.values()) / 12 * 365,
            "source": "NASA POWER Climatology API",
            "units": "kWh/m²/day (monthly avg)",
        }
        print(f"Annual GHI = {result['annual_ghi_kwh_m2_yr']:.1f} kWh/m²/yr")
        return result

    except requests.exceptions.Timeout:
        print("TIMEOUT — skipping")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def upload_to_s3(data: dict, key: str, bucket: str):
    import boto3
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2).encode(),
        ContentType="application/json",
    )
    print(f"    → Uploaded to s3://{bucket}/{key}")


def save_locally(data: dict, out_dir: Path, filename: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"    → Saved locally to {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", help="S3 bucket name to upload to")
    parser.add_argument("--local-only", action="store_true", help="Don't upload to S3")
    parser.add_argument("--out", default="scripts/seed_data/nasa_power", help="Local output dir")
    parser.add_argument("--hp-only", action="store_true", help="Only fetch HP districts (faster)")
    args = parser.parse_args()

    if not args.bucket and not args.local_only:
        print("ERROR: Provide --bucket <name> or --local-only")
        return

    locations = {**HP_DISTRICTS}
    if not args.hp_only:
        locations.update(EXTRA_CITIES)

    out_dir = Path(args.out)
    all_data = {}

    print(f"\nFetching NASA POWER data for {len(locations)} locations...\n")

    for key, info in locations.items():
        data = fetch_ghi(info["lat"], info["lon"], info["label"])
        if data:
            all_data[key] = data
            filename = f"{key}.json"

            if args.local_only or not args.bucket:
                save_locally(data, out_dir, filename)
            else:
                try:
                    upload_to_s3(data, f"nasa_power/{filename}", args.bucket)
                except Exception as e:
                    print(f"    S3 upload failed ({e}) — saving locally")
                    save_locally(data, out_dir, filename)

        time.sleep(0.5)  # Be polite to NASA API

    # Save a combined summary file
    summary = {
        loc: {
            "label": d["label"],
            "annual_ghi_kwh_m2_yr": d["annual_ghi_kwh_m2_yr"],
        }
        for loc, d in all_data.items()
    }

    summary_filename = "summary.json"
    if args.local_only or not args.bucket:
        save_locally(summary, out_dir, summary_filename)
    else:
        try:
            upload_to_s3(summary, f"nasa_power/{summary_filename}", args.bucket)
        except Exception as e:
            save_locally(summary, out_dir, summary_filename)

    print(f"\n✅ Done. Fetched {len(all_data)}/{len(locations)} locations.")
    print("\nGHI Summary (kWh/m²/yr):")
    for loc, d in all_data.items():
        print(f"  {d['label']}: {d['annual_ghi_kwh_m2_yr']:.1f}")


if __name__ == "__main__":
    main()
