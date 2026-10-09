"""
backend/audit_worker/tools/calc_generation.py
"""
import json
import os

import boto3

BUCKET = os.environ["MEDIA_BUCKET"]
s3     = boto3.client("s3")

# CEA Grid Emission Factor FY2023-24
CEA_CO2_KG_PER_KWH = 0.716

# HPSEBL residential tariff (blended for typical 300 unit/month household)
HPSEBL_TARIFF_PER_KWH = 4.50  # ₹/kWh blended (conservative)

# Performance ratio (standard for Indian rooftops)
PERFORMANCE_RATIO = 0.80

# Fallback GHI (kWh/m²/day) for Hamirpur HP if S3 cache unavailable
HAMIRPUR_GHI_FALLBACK = 4.85


def _load_ghi() -> float:
    """Try to load GHI from S3 NASA POWER cache."""
    try:
        obj = s3.get_object(Bucket=BUCKET, Key="nasa_power/hamirpur.json")
        data = json.loads(obj["Body"].read())
        monthly = data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]

        # Filter to only the 12 numeric month keys ("01"–"12").
        # NASA also returns an "ANN" key (annual average) which must be excluded —
        # including it would corrupt both the sum and the divisor.
        monthly_values = [
            v for k, v in monthly.items()
            if k.isdigit() and isinstance(v, (int, float)) and v > 0
        ]

        if not monthly_values:
            raise ValueError("No valid monthly GHI data found in NASA POWER cache")

        avg_daily = sum(monthly_values) / len(monthly_values)   # kWh/m²/day
        return avg_daily * 365                                   # kWh/m²/year
    except Exception as e:
        print(f"[calc_generation] S3 GHI load failed ({e}), using fallback {HAMIRPUR_GHI_FALLBACK}")
        return HAMIRPUR_GHI_FALLBACK * 365


def calc_generation(system_kw: float, lat: float = 31.6862, lon: float = 76.5222) -> dict:
    """
    Estimate annual solar generation.
    
    Formula: Annual_kWh = system_kW × annual_GHI × PR
    Source:  NASA POWER (pre-cached in S3) for Hamirpur, HP
    """
    annual_ghi  = _load_ghi()                          # kWh/m²/year
    annual_kwh  = system_kw * annual_ghi * PERFORMANCE_RATIO
    co2_kg      = annual_kwh * CEA_CO2_KG_PER_KWH
    
    # 25-year lifetime CO2
    lifetime_co2_tonnes = co2_kg * 25 / 1000
    
    # Annual savings (electricity bill)
    annual_savings = annual_kwh * HPSEBL_TARIFF_PER_KWH

    return {
        "annual_kwh":             round(annual_kwh),
        "monthly_avg_kwh":        round(annual_kwh / 12),
        "co2_avoided_kg_yr":      round(co2_kg),
        "co2_avoided_tonnes_yr":  round(co2_kg / 1000, 2),
        "co2_lifetime_tonnes":    round(lifetime_co2_tonnes, 1),
        "annual_savings_inr":     round(annual_savings),
        "ghi_source":             "NASA POWER (AWS Open Data Registry)",
        "performance_ratio":      PERFORMANCE_RATIO,
        "cea_emission_factor":    CEA_CO2_KG_PER_KWH,
    }
