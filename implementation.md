# PakkaSolar — Complete Implementation Plan
> Solo · NIT Hamirpur · Oct 8–11, 2026 · Track 03 Waste & Energy
> **Clock started this morning. It is now ~18:00 Thu. You have roughly 65 hours.**

---

## Part 0: What you need before writing a line of code

### 0.1 AWS account checklist (do this NOW, tonight)

| Task | Where | Status to confirm |
|---|---|---|
| AWS account created | console.aws.amazon.com | — |
| Budget alarm: $10 | Billing → Budgets | "Active" |
| **Bedrock model access** → Amazon Nova Lite + Nova Pro | Bedrock console → Model Access → Request (ap-south-1 or us-east-1) | "Access granted" (can take 5–30 min) |
| Bedrock model access → Amazon Titan Text (fallback) | Same screen | "Access granted" |
| Polly hi-IN voice available | Polly console → Text to speech → Language: Hindi, Voice: Kajal (Neural) | Plays audio |
| SAM CLI installed | `sam --version` in terminal | version ≥ 1.100 |
| AWS CLI configured | `aws sts get-caller-identity` | returns your account ID |
| Node 18+ and Python 3.12 installed | `node -v`, `python --version` | — |

> **Bedrock region note:** Nova multimodal (image reading) is available in **us-east-1** and **us-west-2** as of mid-2026. If ap-south-1 doesn't show Nova, use a **cross-region inference profile** (the console lists them as `us.amazon.nova-lite-v1:0`). Your Lambda sits in ap-south-1; it calls Bedrock via the cross-region profile. This adds ~200ms but costs the same.

### 0.2 External accounts/APIs (do this tonight)

| Service | What you need | Time | Free? |
|---|---|---|---|
| **Meta WhatsApp Cloud API** | Business account → test number → webhook URL | 30–60 min | Yes (5 verified test recipients) |
| **NASA POWER API** | No key needed for `https://power.larc.nasa.gov/api/temporal/...` | 0 min | Yes |
| **MNRE ALMM PDFs** | Download List-I (modules) and List-II (cells) from mnre.gov.in | 10 min | Public |
| **PM Surya Ghar vendor page** | Manually copy HP empanelled vendor list (30–50 rows) | 30 min | Public |
| GitHub repo | Create NOW, first commit tonight | 5 min | Free |

---

## Part 1: Data layer — prepare this Thursday night

This is the unsexy work that makes the demo credible. Do it before touching any Lambda.

### 1.1 ALMM Panel database

**Source:** MNRE → `mnre.gov.in` → ALMM List-I (Solar PV Modules) PDF

**What the PDF contains:** Manufacturer name · Model series · Cell type (Mono-PERC, TOPCon, etc.) · DCR certified (Yes/No) · Date added

**Your strategy (4 steps):**

1. Download the PDF. Open it. It has ~80–200 rows.
2. Use `pdfplumber` to extract tables. Expect messy output—some cells merge, some rows span pages.
3. Clean it into a CSV: `brand | model_prefix | dcr_certified | cell_type | list_version | added_date`
4. Upload to DynamoDB table `almm_panels` (see schema below).

**Fallback if PDF parsing takes >2 hours:** Hand-curate the **top 30 Indian solar brands by market share** (Waaree, Adani Solar, Vikram Solar, Tata Power Solar, Goldi Solar, Renewsys, Emmvee, Saatvik, Premier, Patanjali Solar). This covers ~85% of quotes you'll see. For anything unknown, the tool returns `"Unknown model – ask vendor for ALMM certificate"`.

**DynamoDB table: `almm_panels`**
```
PK: brand_normalized (lowercase, no spaces, e.g. "waaree")
SK: model_prefix (e.g. "ws540", "ws-540", "540m")
Attributes:
  brand_display: "Waaree"
  dcr_certified: true/false
  cell_type: "Mono-PERC"
  list_version: "List-I v2026-Q2"
  list_date: "2026-04-01"
  watt_range_min: 500
  watt_range_max: 600
```

> **Lookup strategy:** Bedrock extracts `"Waaree 540W mono"`. Your tool normalizes → `brand="waaree"`, `watt=540`, does a DynamoDB query on PK="waaree" and filters by watt_range. If no exact match, returns `dcr_uncertain: true`.

### 1.2 Vendor empanelment database

**Source:** `pmsuryaghar.gov.in` → Vendor List → Filter by State: Himachal Pradesh

The page is JS-heavy. Use the browser's Network tab → find the JSON API it calls → `curl` that directly.

**DynamoDB table: `vendors`**
```
PK: state_code (e.g. "HP")
SK: vendor_name_normalized (e.g. "sharma_solar_hamirpur")
Attributes:
  vendor_display: "Sharma Solar, Hamirpur"
  discom: "HPSEBL"
  empanelled: true
  last_verified: "2026-10-08"
  district: "Hamirpur"
```

**Lookup strategy:** Bedrock extracts `"Sharma Solar"` from the quote. Tool normalizes → strips "Pvt Ltd", "& Sons", etc. → fuzzy matches against `vendor_name_normalized` using Python `difflib.get_close_matches`. Threshold: 0.7 similarity. If below threshold → `"Vendor not found in HP registry"`.

Seed at least **20 HP vendors** by hand tonight. Mark 3–4 as `empanelled: false` for the demo's "FAIL" case.

### 1.3 Subsidy + tariff reference (hardcode in Lambda env vars or a DynamoDB config table)

| Key | Value | Source |
|---|---|---|
| Subsidy per kW (1–2 kW) | ₹30,000/kW | pmsuryaghar.gov.in |
| Subsidy per kW (3rd kW) | ₹18,000/kW | pmsuryaghar.gov.in |
| Max subsidy (general) | ₹78,000 | Portal |
| Max subsidy (special category — HP) | ₹85,800 | Portal (10% extra for HP, J&K, NE, Uttarakhand) |
| MNRE benchmark price (3 kW, HP) | ₹1,65,000–₹1,85,000 | MNRE circular (curate this; show source) |
| CEA CO₂ factor | 0.716 kg CO₂/kWh | CEA Baseline Document FY24 |
| HPSEBL residential tariff (0–125 units) | ₹3.50/unit | HPERC tariff order (verify) |
| HPSEBL residential tariff (125–300 units) | ₹4.80/unit | HPERC tariff order |

### 1.4 NASA POWER solar data (pre-cache for Hamirpur)

NASA POWER API endpoint (no key needed):
```
GET https://power.larc.nasa.gov/api/temporal/climatology/point
  ?parameters=ALLSKY_SFC_SW_DWN
  &community=RE
  &longitude=76.5222
  &latitude=31.6862
  &format=JSON
```

This returns monthly average Global Horizontal Irradiance (GHI) in kWh/m²/day for Hamirpur.

**Pre-cache this response in S3** as `nasa_power/hamirpur.json` tonight. In the tool, for any HP district, use the Hamirpur value. For other states, hardcode 3–5 major cities. If the user's pincode resolves to a different district, fall back to the state capital.

**Generation estimate formula:**
```
Annual_kWh = system_kW × GHI_annual × Performance_Ratio
           = system_kW × (monthly_avg × 365) × 0.80
CO2_annual_kg = Annual_kWh × 0.716
```

---

## Part 2: Backend architecture (the full under-the-hood flow)

### 2.1 High-level flow

```
[User uploads image]
        │
        ▼
[API Gateway — HTTP API]
        │ POST /audit
        ▼
[Lambda: webhook_handler]
  • Validates Content-Type
  • Generates audit_id (UUID)
  • Puts image in S3: uploads/{audit_id}.jpg
  • Sends SQS message: {audit_id, source: "web"|"whatsapp", user_lang: "hi"|"en"}
  • Returns: 202 {"audit_id": "abc-123", "poll_url": "/status/abc-123"}
        │
        ▼ (async, decoupled)
[SQS Queue: audit-queue]
  Visibility timeout: 120s
  DLQ after 3 failures
        │
        ▼
[Lambda: audit_worker] (triggered by SQS)
  • Pulls image from S3
  • Runs Strands Agent (see Part 3)
  • Stores result in DynamoDB: audits table
  • Calls Polly → saves voice note to S3: verdicts/{audit_id}.mp3
  • Generates verdict HTML page → S3: verdicts/{audit_id}.html
        │
        ▼
[DynamoDB: audits table]
  • Frontend polls GET /status/{audit_id} every 2s
  • When status="complete", frontend fetches verdict
```

**Why SQS?** The WhatsApp webhook requires a response in 3 seconds. Bedrock Nova multimodal takes 8–15 seconds. Without SQS you'd time out. This is an enterprise-grade pattern—mention it in the video.

### 2.2 DynamoDB tables summary

| Table | PK | SK | Purpose |
|---|---|---|---|
| `almm_panels` | `brand_normalized` | `model_prefix` | Panel DCR lookup |
| `vendors` | `state_code` | `vendor_name_normalized` | Vendor empanelment |
| `audits` | `audit_id` | — | Audit state + results |
| `config` | `key` | — | Subsidy rates, tariffs |

**`audits` table schema:**
```
audit_id: "abc-123"           # PK
status: "pending"|"complete"|"failed"
created_at: ISO timestamp
source: "web"|"whatsapp"
user_lang: "hi"|"en"
# Set by worker on completion:
extracted:
  system_kw: 3
  brand: "Waaree"
  model: "WS 540W"
  vendor: "Sharma Solar"
  quoted_price: 190000
checks:
  panel_dcr: "PASS"|"FAIL"|"UNCERTAIN"
  panel_dcr_detail: "Waaree WS-540 found in ALMM List-I v2026-Q2"
  vendor_empanelled: "PASS"|"FAIL"|"NOT_FOUND"
  vendor_detail: "Sharma Solar registered under HPSEBL HP"
  price_check: "PASS"|"AMBER"|"FAIL"
  price_detail: "₹63,333/kW — within MNRE benchmark ₹55,000–₹65,000/kW"
  subsidy_eligible: true
  subsidy_amount: 85800
  generation_kwh_yr: 4350
  co2_kg_yr: 3115
verdict: "RED"|"AMBER"|"GREEN"
verdict_summary_hi: "..."
verdict_summary_en: "..."
voice_note_url: "https://cdn.pakkasolar.in/verdicts/abc-123.mp3"
verdict_page_url: "https://cdn.pakkasolar.in/verdicts/abc-123.html"
vendor_message: "Sharma Ji, kripya mera quote ..."
```

### 2.3 Lambda configuration

| Lambda | Runtime | Memory | Timeout | Trigger |
|---|---|---|---|---|
| `webhook_handler` | Python 3.12 | 256 MB | 10s | API Gateway |
| `audit_worker` | Python 3.12 | 1024 MB | 120s | SQS |
| `status_handler` | Python 3.12 | 128 MB | 5s | API Gateway |

### 2.4 API Gateway routes

```
POST /audit          → webhook_handler     (image upload)
GET  /status/{id}   → status_handler      (poll for result)
POST /webhook/wa    → webhook_handler     (WhatsApp webhook)
GET  /webhook/wa    → webhook_handler     (WhatsApp verification challenge)
```

---

## Part 3: The Strands Agent (the brain)

### 3.1 Agent overview

```python
# audit_worker/agent.py
from strands import Agent
from strands_tools import tool
from strands.models import BedrockModel

model = BedrockModel(
    model_id="us.amazon.nova-pro-v1:0",   # cross-region inference profile
    region_name="us-east-1"
)

agent = Agent(
    model=model,
    tools=[
        parse_quote,
        check_almm,
        check_vendor,
        calc_subsidy,
        calc_generation,
        check_price,
        build_verdict,
    ],
    system_prompt=SYSTEM_PROMPT
)
```

**System prompt (critical — copy this exactly):**
```
You are PakkaSolar, an AI auditor for Indian residential rooftop solar quotes.
Your job is to audit a solar quote image step by step using the provided tools.
You MUST call every tool in order. Do NOT skip any tool.
Do NOT guess. If a tool returns UNCERTAIN, report it as UNCERTAIN.
Do NOT hallucinate panel models or vendor names.
Always output a structured JSON verdict at the end.
Respond in the user's language: {user_lang}.
```

### 3.2 Tool definitions

```python
@tool
def parse_quote(image_s3_key: str) -> dict:
    """
    Extract solar quote details from an image using Amazon Bedrock Nova multimodal.
    Returns: system_kw, brand, model, vendor_name, quoted_price, warranty_years
    """
    import boto3, base64
    s3 = boto3.client('s3')
    img = s3.get_object(Bucket=BUCKET, Key=image_s3_key)['Body'].read()
    img_b64 = base64.b64encode(img).decode()
    
    bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
    response = bedrock.invoke_model(
        modelId='us.amazon.nova-pro-v1:0',
        body=json.dumps({
            "messages": [{
                "role": "user",
                "content": [
                    {"image": {"format": "jpeg", "source": {"bytes": img_b64}}},
                    {"text": QUOTE_EXTRACTION_PROMPT}
                ]
            }],
            "inferenceConfig": {"maxTokens": 500}
        })
    )
    # parse JSON from response → validate with Pydantic schema
    return QuoteSchema(**parsed).model_dump()
```

**`QUOTE_EXTRACTION_PROMPT`:**
```
Extract the following from this solar quote image and return ONLY valid JSON:
{
  "system_kw": <number, total kW capacity>,
  "brand": "<panel brand name>",
  "model": "<panel model number if visible>",
  "vendor_name": "<company selling this quote>",
  "quoted_price": <total price in INR as integer>,
  "warranty_years": <performance warranty years if stated, else null>
}
If any field is not clearly readable, set it to null. Do NOT guess.
```

**Pydantic validation schema:**
```python
from pydantic import BaseModel
from typing import Optional

class QuoteSchema(BaseModel):
    system_kw: float
    brand: Optional[str] = None
    model: Optional[str] = None
    vendor_name: Optional[str] = None
    quoted_price: Optional[int] = None
    warranty_years: Optional[int] = None
```

---

```python
@tool
def check_almm(brand: str, model: Optional[str], system_kw: float) -> dict:
    """
    Check if the panel brand/model is on MNRE's ALMM DCR list.
    Returns: dcr_status (PASS/FAIL/UNCERTAIN), detail, list_version
    """
    import boto3
    from difflib import get_close_matches
    
    ddb = boto3.resource('dynamodb').Table('almm_panels')
    brand_norm = normalize(brand)  # lowercase, remove spaces
    
    # Query all models for this brand
    result = ddb.query(KeyConditionExpression=Key('brand_normalized').eq(brand_norm))
    
    if not result['Items']:
        # Try fuzzy match on brand
        all_brands = get_all_brands()  # cached in Lambda global
        matches = get_close_matches(brand_norm, all_brands, n=1, cutoff=0.7)
        if matches:
            brand_norm = matches[0]
            result = ddb.query(...)
        else:
            return {"dcr_status": "UNCERTAIN", "detail": f"Brand '{brand}' not found in ALMM database. Ask vendor for ALMM certificate.", "list_version": ALMM_VERSION}
    
    # Check watt range match
    watt = system_kw * 1000 / 6  # assume 6 panels for 3kW (rough)
    for item in result['Items']:
        if item['watt_range_min'] <= watt <= item['watt_range_max']:
            if item['dcr_certified']:
                return {"dcr_status": "PASS", "detail": f"{item['brand_display']} {model} found in {item['list_version']}.", "list_version": item['list_version']}
            else:
                return {"dcr_status": "FAIL", "detail": f"{item['brand_display']} panels in this watt range are NOT DCR certified. Subsidy will be rejected.", "list_version": item['list_version']}
    
    return {"dcr_status": "UNCERTAIN", "detail": "Model found but watt range unclear. Request ALMM certificate from vendor."}
```

---

```python
@tool
def check_vendor(vendor_name: str, state: str = "HP") -> dict:
    """
    Check if vendor is empanelled under PM Surya Ghar in the given state.
    Returns: empanelled (PASS/FAIL/NOT_FOUND), detail
    """
    # fuzzy match against DynamoDB vendors table
    ...
```

---

```python
@tool
def calc_subsidy(system_kw: float, state: str = "HP") -> dict:
    """
    Calculate PM Surya Ghar subsidy for given system size and state.
    Returns: subsidy_amount, eligible, breakdown
    """
    special_category_states = ["HP", "JK", "UK", "NE"]  # 10% extra
    multiplier = 1.10 if state in special_category_states else 1.0
    
    if system_kw <= 2:
        base = system_kw * 30000
    else:
        base = 2 * 30000 + min(system_kw - 2, 1) * 18000
    
    cap = 78000 * multiplier  # 85800 for HP
    subsidy = min(base * multiplier, cap)
    
    return {
        "subsidy_amount": int(subsidy),
        "eligible": True,
        "breakdown": f"₹{int(subsidy):,} (includes HP special category 10% bonus)",
        "cap": int(cap)
    }
```

---

```python
@tool
def calc_generation(system_kw: float, lat: float = 31.6862, lon: float = 76.5222) -> dict:
    """
    Estimate annual solar generation using NASA POWER data (pre-cached in S3).
    Returns: annual_kwh, monthly_avg_kwh, co2_avoided_kg_yr, payback_years
    """
    import boto3, json
    
    # Try to load cached NASA POWER data
    s3 = boto3.client('s3')
    try:
        obj = s3.get_object(Bucket=BUCKET, Key='nasa_power/hamirpur.json')
        data = json.loads(obj['Body'].read())
        annual_ghi = sum(data['properties']['parameter']['ALLSKY_SFC_SW_DWN'].values())
        # annual_ghi is in kWh/m²/yr
    except:
        annual_ghi = 5.0 * 365  # fallback: 5 kWh/m²/day average for HP
    
    annual_kwh = system_kw * annual_ghi * 0.80  # PR = 0.80
    co2_kg = annual_kwh * 0.716  # CEA factor
    
    return {
        "annual_kwh": round(annual_kwh),
        "co2_avoided_kg_yr": round(co2_kg),
        "co2_avoided_tonnes_yr": round(co2_kg / 1000, 2),
        "data_source": "NASA POWER (AWS Open Data)"
    }
```

---

```python
@tool
def check_price(quoted_price: int, system_kw: float, state: str = "HP") -> dict:
    """
    Check if quoted price is within MNRE benchmark range.
    Returns: status (PASS/AMBER/FAIL), price_per_kw, benchmark_range, detail
    """
    price_per_kw = quoted_price / system_kw
    # MNRE benchmark for HP (special category): ₹55,000–₹70,000/kW inclusive of everything
    # Adjust based on system size
    benchmark_low = 55000
    benchmark_high = 70000
    
    if price_per_kw < benchmark_low * 0.85:
        return {"status": "AMBER", "detail": "Unusually low price. May indicate non-DCR or substandard panels.", "price_per_kw": int(price_per_kw)}
    elif price_per_kw > benchmark_high * 1.20:
        return {"status": "AMBER", "detail": f"Price ₹{int(price_per_kw):,}/kW is above typical range. Negotiate.", "price_per_kw": int(price_per_kw)}
    else:
        return {"status": "PASS", "detail": f"Price ₹{int(price_per_kw):,}/kW is within MNRE benchmark range.", "price_per_kw": int(price_per_kw)}
```

---

```python
@tool
def build_verdict(panel_result: dict, vendor_result: dict, price_result: dict, 
                  subsidy_result: dict, generation_result: dict,
                  extracted: dict, user_lang: str = "hi") -> dict:
    """
    Assemble final verdict card. Returns structured verdict + Hindi/English summary.
    """
    # Determine overall RAG status
    if panel_result['dcr_status'] == 'FAIL':
        verdict = "RED"
    elif panel_result['dcr_status'] == 'UNCERTAIN' or vendor_result['empanelled'] == 'NOT_FOUND':
        verdict = "AMBER"
    else:
        verdict = "GREEN"
    
    # Generate vendor message
    if verdict in ["RED", "AMBER"]:
        vendor_msg = generate_vendor_message(extracted, panel_result, user_lang)
    else:
        vendor_msg = None
    
    return {
        "verdict": verdict,
        "summary_hi": HINDI_SUMMARIES[verdict],
        "summary_en": ENGLISH_SUMMARIES[verdict],
        "vendor_message": vendor_msg,
        "checks": {
            "panel_dcr": panel_result,
            "vendor": vendor_result,
            "price": price_result,
        },
        "subsidy": subsidy_result,
        "generation": generation_result
    }
```

### 3.3 Polly voice note generation

```python
def generate_voice_note(verdict_data: dict, audit_id: str, lang: str = "hi") -> str:
    """Generate Hindi voice note via Amazon Polly, save to S3."""
    import boto3
    
    polly = boto3.client('polly')
    s3 = boto3.client('s3')
    
    text = build_polly_text(verdict_data, lang)  # see below
    
    response = polly.synthesize_speech(
        Engine='neural',
        LanguageCode='hi-IN',
        VoiceId='Kajal',       # Only neural Hindi voice
        Text=text,
        OutputFormat='mp3',
        TextType='text'        # use 'ssml' for pauses/emphasis
    )
    
    key = f"verdicts/{audit_id}.mp3"
    s3.put_object(Bucket=BUCKET, Key=key, Body=response['AudioStream'].read(), ContentType='audio/mpeg')
    return f"https://{CLOUDFRONT_DOMAIN}/{key}"
```

**Polly text template (Hindi, RED verdict):**
```
Namaste! PakkaSolar ki taraf se aapke quote ki jaanch poori ho gayi hai.

Hamare AI agent ne paaya ki aapke quote mein likhe panels, Sarkar ki DCR approved list par nahin hain.
Iska matlab hai, agar yahi panels lagaye gaye, toh aapko 85,800 rupaye ki subsidy nahin milegi.

Turat apne vendor se kehan: "Mujhe ALMM list mein shamil, DCR certified panels ka quote chahiye."

Agar vendor saaf jawab nahin deta, toh naye vendor ko chunein.

PakkaSolar ke saath, apna paisa surakshit rakhein. Sign karne se pehle jaanch karein.
```

---

## Part 4: Frontend (React/Vite)

### 4.1 Page structure

Single-page app. **4 screens, no routing needed — just conditional rendering.**

```
Screen 1: Upload
Screen 2: Confirmation (human-in-the-loop)
Screen 3: Processing (spinner)
Screen 4: Verdict card
```

### 4.2 Screen 1 — Upload

```
┌─────────────────────────────┐
│  🌞 PakkaSolar              │
│  [EN] [हि]                   │
│                             │
│  ╔═══════════════════════╗  │
│  ║  📷 Quote upload      ║  │
│  ║  Tap to upload photo  ║  │
│  ║  of your solar quote  ║  │
│  ╚═══════════════════════╝  │
│                             │
│  [Upload Quote]             │
│                             │
│  ── or drag & drop ──       │
└─────────────────────────────┘
```

- File input: `accept="image/*,application/pdf"`
- On select: compress image client-side to max 1MB using `browser-image-compression` npm package (keeps upload fast on 3G)
- POST to `/audit` as multipart form
- Store `audit_id` in component state, move to Screen 3

### 4.3 Screen 2 — Confirmation (human-in-the-loop)

Shown AFTER Bedrock extracts the quote but BEFORE running the checks.

This requires a two-phase design in the worker:
1. Worker extracts quote → saves `extracted` to DynamoDB → status = `"needs_confirmation"`
2. Frontend shows confirmation screen
3. User clicks Yes/Edit → POST `/confirm/{audit_id}` → SQS message to continue

```
┌─────────────────────────────┐
│  I read your quote as:      │
│                             │
│  System:  3 kW              │
│  Panels:  Waaree 540W Mono  │
│  Vendor:  Sharma Solar      │
│  Price:   ₹1,90,000         │
│                             │
│  [✓ Yes, correct]           │
│  [✎ Edit]                   │
└─────────────────────────────┘
```

> **Demo note:** For the video, pre-seed a quote that parses cleanly. The confirmation step is your **human-in-the-loop** moment — mention it explicitly in the video. This is what separates you from an LLM wrapper.

### 4.4 Screen 3 — Processing

```
┌─────────────────────────────┐
│  🔍 Analyzing...            │
│                             │
│  ✓ Quote read               │
│  ⟳ Checking DCR panels...   │
│  - Checking HP vendors      │
│  - Calculating subsidy      │
└─────────────────────────────┘
```

Poll `/status/{audit_id}` every 2 seconds. Animate the checklist as results come in. When `status === "complete"`, transition to Screen 4.

### 4.5 Screen 4 — Verdict card

```
┌─────────────────────────────┐
│ 🔴 SUBSIDY AT RISK          │
│                             │
│ Panel Check    🔴 FAIL      │
│ These panels not on DCR     │
│ list. Subsidy will be lost. │
│                             │
│ Vendor Check   🟢 PASS      │
│ Sharma Solar is registered  │
│ in HP under HPSEBL.         │
│                             │
│ Price Check    🟢 PASS      │
│ ₹63,333/kW — within range.  │
│ ─────────────────────────── │
│ Your HP subsidy: ₹85,800    │
│ CO₂ avoided: 3.1 t/year     │
│ Generation: 4,350 kWh/year  │
│ ─────────────────────────── │
│ 🔊 [Play Hindi voice note]  │
│                             │
│ [📋 Copy message to vendor] │
│ [🔁 Check another quote]    │
└─────────────────────────────┘
```

The vendor message (pre-filled for clipboard):
```
Sharma Ji, mera quote dobara bhejein — sirf ALMM List mein shamil DCR 
certified panels ke saath. Bina DCR panels ke mujhe ₹85,800 ki PM Surya 
Ghar subsidy nahin milegi. MNRE ki approved list yahan dekhein: 
mnre.gov.in/ALMM
```

### 4.6 Key frontend implementation notes

- **Hindi/English toggle:** use a `lang` state variable. All strings in a `strings.js` object with `hi` and `en` keys.
- **Zero web fonts on verdict page.** System fonts only. Loads on 2G.
- **Embed audio player** using native `<audio>` tag. No library needed.
- **Color-blind safe:** use icons (✓/✗/?) alongside colors. Never rely on color alone.
- **Touch targets:** minimum 48×48px for all buttons (WCAG).
- **Text size:** minimum 16px body, 20px key verdicts.

---

## Part 5: Infrastructure as Code (SAM)

### 5.1 `template.yaml` structure

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Globals:
  Function:
    Runtime: python3.12
    Environment:
      Variables:
        BUCKET: !Ref MediaBucket
        ALMM_TABLE: !Ref AlmmTable
        VENDORS_TABLE: !Ref VendorsTable
        AUDITS_TABLE: !Ref AuditsTable
        CLOUDFRONT_DOMAIN: !GetAtt CFDistribution.DomainName
        BEDROCK_REGION: us-east-1

Resources:
  # API Gateway
  PakkaApi:
    Type: AWS::Serverless::Api
    Properties:
      StageName: prod
      Cors:
        AllowOrigins: "'*'"
        AllowHeaders: "'Content-Type'"

  # Lambda functions
  WebhookHandler:
    Type: AWS::Serverless::Function
    Properties:
      Handler: webhook_handler.lambda_handler
      Timeout: 10
      MemorySize: 256
      Events:
        Upload: {Type: Api, Properties: {RestApiId: !Ref PakkaApi, Path: /audit, Method: POST}}
        Status: {Type: Api, Properties: {RestApiId: !Ref PakkaApi, Path: /status/{audit_id}, Method: GET}}
        WAVerify: {Type: Api, Properties: {RestApiId: !Ref PakkaApi, Path: /webhook/wa, Method: GET}}
        WAWebhook: {Type: Api, Properties: {RestApiId: !Ref PakkaApi, Path: /webhook/wa, Method: POST}}

  AuditWorker:
    Type: AWS::Serverless::Function
    Properties:
      Handler: audit_worker.lambda_handler
      Timeout: 120
      MemorySize: 1024
      Events:
        SQSTrigger:
          Type: SQS
          Properties:
            Queue: !GetAtt AuditQueue.Arn
            BatchSize: 1
      Policies:
        - AmazonDynamoDBFullAccess
        - AmazonS3FullAccess
        - AmazonPollyFullAccess
        - Statement:
            Effect: Allow
            Action: bedrock:InvokeModel
            Resource: "*"

  # SQS
  AuditQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 120
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt AuditDLQ.Arn
        maxReceiveCount: 3

  AuditDLQ:
    Type: AWS::SQS::Queue

  # DynamoDB tables
  AlmmTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: almm_panels
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - {AttributeName: brand_normalized, AttributeType: S}
        - {AttributeName: model_prefix, AttributeType: S}
      KeySchema:
        - {AttributeName: brand_normalized, KeyType: HASH}
        - {AttributeName: model_prefix, KeyType: RANGE}

  VendorsTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: vendors
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - {AttributeName: state_code, AttributeType: S}
        - {AttributeName: vendor_name_normalized, AttributeType: S}
      KeySchema:
        - {AttributeName: state_code, KeyType: HASH}
        - {AttributeName: vendor_name_normalized, KeyType: RANGE}

  AuditsTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: audits
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - {AttributeName: audit_id, AttributeType: S}
      KeySchema:
        - {AttributeName: audit_id, KeyType: HASH}
      TimeToLiveSpecification:
        AttributeName: ttl
        Enabled: true

  # S3 + CloudFront
  MediaBucket:
    Type: AWS::S3::Bucket
    Properties:
      CorsConfiguration:
        CorsRules:
          - AllowedMethods: [GET, PUT, POST]
            AllowedOrigins: ["*"]
            AllowedHeaders: ["*"]

  CFDistribution:
    Type: AWS::CloudFront::Distribution
    # ... standard S3 origin config
```

### 5.2 Local development

```bash
# Start local API (no AWS needed)
sam local start-api --env-vars env.local.json

# env.local.json
{
  "WebhookHandler": {
    "BUCKET": "local-bucket",
    "USE_MOCK_BEDROCK": "true"
  },
  "AuditWorker": {
    "USE_MOCK_BEDROCK": "true",
    "USE_MOCK_POLLY": "true"
  }
}
```

Add `USE_MOCK_BEDROCK` flag to your worker. When true, return a hardcoded parsed quote (this lets judges run `make local` without AWS credentials — copy Beacon's pattern).

```makefile
# Makefile
local:
    USE_MOCK_BEDROCK=true sam local start-api --env-vars env.local.json

deploy:
    sam build && sam deploy --guided

seed:
    python scripts/seed_dynamo.py  # loads ALMM + vendor data
```

---

## Part 6: Project structure

```
pakkasolar/
├── template.yaml              # SAM IaC
├── Makefile                   # make local, make deploy, make seed
├── README.md
├── docs/
│   ├── architecture.png       # diagram for README
│   └── demo.gif               # recording for README header
│
├── frontend/                  # React/Vite
│   ├── src/
│   │   ├── App.jsx
│   │   ├── screens/
│   │   │   ├── Upload.jsx
│   │   │   ├── Confirmation.jsx
│   │   │   ├── Processing.jsx
│   │   │   └── Verdict.jsx
│   │   ├── strings.js         # all Hindi/English UI strings
│   │   ├── api.js             # fetch wrappers for /audit /status
│   │   └── index.css
│   ├── vite.config.js
│   └── package.json
│
├── backend/
│   ├── webhook_handler/
│   │   ├── lambda_function.py
│   │   └── requirements.txt
│   ├── audit_worker/
│   │   ├── lambda_function.py
│   │   ├── agent.py           # Strands agent definition
│   │   ├── tools/
│   │   │   ├── parse_quote.py
│   │   │   ├── check_almm.py
│   │   │   ├── check_vendor.py
│   │   │   ├── calc_subsidy.py
│   │   │   ├── calc_generation.py
│   │   │   ├── check_price.py
│   │   │   └── build_verdict.py
│   │   ├── polly.py
│   │   ├── models.py          # Pydantic schemas
│   │   └── requirements.txt
│   └── status_handler/
│       ├── lambda_function.py
│       └── requirements.txt
│
├── scripts/
│   ├── seed_dynamo.py         # loads ALMM + vendor CSV → DynamoDB
│   ├── parse_almm_pdf.py      # PDF → CSV using pdfplumber
│   ├── fetch_nasa_power.py    # downloads + caches Hamirpur data → S3
│   └── seed_data/
│       ├── almm_panels.csv    # manually curated ALMM subset
│       └── vendors_hp.csv     # HP vendor list
│
└── tests/
    ├── test_tools.py           # unit tests for each tool (moto mocks)
    ├── test_agent.py           # integration test with mock Bedrock
    └── sample_quotes/
        ├── quote_pass.jpg     # GREEN verdict test case
        ├── quote_fail_dcr.jpg # RED verdict test case
        └── quote_uncertain.jpg
```

---

## Part 7: Hour-by-hour schedule (revised — clock started 10:00, it is now 18:00)

### Thursday Oct 8 (tonight, 18:00–24:00) — Foundation

| Time | Task | Done when |
|---|---|---|
| 18:00–18:30 | GitHub repo created, first commit (`feat: initial project scaffold`), Bedrock model access requested | Repo public, Bedrock pending/granted |
| 18:30–19:30 | `sam init` → skeleton template · 3 Lambda stubs · 4 DynamoDB tables · S3 bucket | `sam build` succeeds |
| 19:30–20:30 | `seed_dynamo.py` + ALMM PDF → CSV (top 30 brands hand-curated) + HP vendor list | Script runs, DynamoDB has data |
| 20:30–21:00 | `fetch_nasa_power.py` → upload to S3 | `hamirpur.json` in S3 |
| 21:00–22:30 | `webhook_handler`: receive image → S3 → SQS → return 202. **Deploy and test with curl.** | `curl -F file=@quote.jpg https://api.../audit` returns `{"audit_id":"..."}` |
| 22:30–24:00 | `audit_worker` skeleton: pull from SQS → call `parse_quote` tool with real Bedrock → save to DynamoDB. **No other tools yet.** | SQS message consumed, `audits` table has extracted data |

### Friday Oct 9 — Core agent + verdict

| Time | Task | Done when |
|---|---|---|
| 08:00–10:00 | All remaining tools: `check_almm`, `check_vendor`, `calc_subsidy`, `calc_generation`, `check_price`, `build_verdict` | Each tool passes unit test in `moto` |
| 10:00–12:00 | Wire all tools into Strands agent. Run end-to-end with a real quote photo. | Verdict JSON in `audits` table |
| 12:00–13:00 | Polly voice note generation + S3 upload | MP3 accessible via URL |
| 13:00–15:00 | React frontend: Screens 1–4. Wire to real API. | Upload → spinner → verdict renders in browser |
| 15:00–16:00 | `status_handler` Lambda + frontend polling | Verdict auto-loads after ~15s |
| 16:00–18:00 | Hindi/English toggle · Verdict card styling · Audio player · Copy-to-clipboard | All UI features work on mobile |
| 18:00–20:00 | Frontend on S3 + CloudFront. CORS. Mobile test on your phone. | Opens on phone browser, uploads work |
| 20:00–22:00 | WhatsApp webhook (if setup < 2hrs; else skip) | WhatsApp photo → verdict (optional) |
| 22:00–24:00 | 10 test quotes (5 real from HP groups, 5 synthetic). Fix edge cases. Architecture diagram v1. | All 10 pass end-to-end |

### Saturday Oct 10 — Polish + real users

| Time | Task | Done when |
|---|---|---|
| 08:00–10:00 | Error handling: Bedrock misread → retry with Textract · unknown brand → UNCERTAIN path · PDF quotes | Error paths don't crash |
| 10:00–12:00 | `make local` with `USE_MOCK_BEDROCK=true` (Beacon pattern for judges) | Works without AWS credentials |
| 12:00–14:00 | **Real user sessions** (2–3 faculty/family/HP solar groups). Film one with consent. | At least 1 usable clip |
| 14:00–16:00 | Fix what testing revealed. CloudWatch dashboard. `$5 budget alarm` screenshot. | CloudWatch shows real invocations |
| 16:00–18:00 | `docs/decisions.md` (why SQS, why Nova, why Strands, trade-offs) | File exists in repo |
| 18:00–20:00 | Seed demo data (3 specific quotes: RED, AMBER, GREEN). Test each. Record raw screen clips. | All 3 clips saved |
| **20:00** | **🔒 FEATURE FREEZE** | — |
| 20:00–22:00 | README draft + architecture diagram final | README renders cleanly on GitHub mobile |
| 22:00–24:00 | Video script + voiceover dry run | You can deliver it in < 3:00 |

### Sunday Oct 11 — Video + submit

| Time | Task | Done when |
|---|---|---|
| 07:00–10:00 | **Video edit:** `scrcpy` phone screen + voiceover + captions + architecture animation. Export. | MP4 under 3:00 |
| 10:00–11:00 | Upload YouTube → unlisted → test incognito. README final: GIF at top, diagram, "Try in 2 min" section. | Incognito plays correctly |
| 11:00–12:00 | Builder Center blog (title: "The ₹85,800 Checkbox") | Published, linked in README |
| 12:00–13:00 | Pre-submission checklist (see Phase 8 of strategy doc) | All 9 boxes checked |
| 13:00 | **SUBMIT** (do not wait until deadline) | Confirmation email received |

---

## Part 8: Video flow (high level — flesh out after build)

This is the storyboard. You don't need to script the voiceover yet, but know the shape.

| Time | Shot | What it proves |
|---|---|---|
| 0:00–0:12 | A printed quote in hand + Hamirpur rooftop shot you filmed + big text "₹85,800 REJECTED" | Hook. Real place. Real problem. |
| 0:12–0:30 | Stats card: 1 crore homes targeted · ₹75,000 crore scheme · 100-page ALMM PDF | Scale of the problem |
| 0:30–0:40 | Persona card (or real user) with a quote | Who is this for |
| 0:40–1:40 | **Uncut** phone screen: upload → confirmation → spinner with checklist animating → RED verdict card → Hindi Polly plays → copy message button | The product. Do NOT cut here. |
| 1:40–1:50 | Same flow on web (laptop) in 10 seconds | Judges can try it without WhatsApp |
| 1:50–2:20 | Architecture diagram animating (highlight SQS, Strands, Nova, Polly) + `sam deploy` terminal | AWS is the brain, not a bolt-on |
| 2:20–2:45 | CloudWatch screenshot + pilot numbers ("12 audits, 3 flagged, ₹2.57L protected") + real user clip if available | Impact |
| 2:45–2:55 | Logo + URL + "Check before you sign." | Close |

**Recording tools:**
- `scrcpy` for phone screen at 1080p
- OBS or Loom for the architecture animation
- Phone mic close to mouth, quiet room, no background music under voice
- Burn in captions (English subtitles minimum, Hindi on-screen text is a bonus)

---

## Part 9: Availability and risk summary

| Dependency | Available? | Risk | Mitigation |
|---|---|---|---|
| Bedrock Nova Lite/Pro (us-east-1) | ✅ Available, need model access request | Access takes 5–30 min; rarely denied for Nova | Request immediately. Fallback: Claude 3 Haiku (always available) |
| Strands Agents SDK (pip) | ✅ `pip install strands-agents strands-agents-tools` | Occasional breaking changes | Pin to a specific version in requirements.txt |
| Amazon Polly `Kajal` neural Hindi | ✅ Available in ap-south-1 | None | — |
| NASA POWER API | ✅ No key, public | Rate limits if you hammer it | Pre-cache in S3 tonight |
| ALMM PDF parsing | ⚠️ PDF quality varies | Parser fails on scanned/image PDFs | Hand-curate top 30 brands as fallback CSV |
| PM Surya Ghar vendor list | ⚠️ JS-heavy site | Scrape may fail | Use browser Network tab to find JSON endpoint; hand-copy HP list |
| Meta WhatsApp Cloud API | ⚠️ Setup takes 30–60 min | Verification can stall | Do web flow first; add WhatsApp only if setup < 1hr |
| SQS → Lambda trigger | ✅ Fully supported in SAM | None | — |
| S3 + CloudFront | ✅ Free tier | None | — |
| SAM CLI deploy | ✅ | First deploy needs `--guided` to set region/S3 bucket | Run `sam deploy --guided` on Thursday night |
| `pdfplumber` on Lambda | ✅ | Binary dependencies; use Lambda layer or Docker-based SAM build | Add `poppler-utils` layer or use `sam build --use-container` |

---

## Part 10: The one thing that must work

If everything else breaks, this single path must run end-to-end by Saturday 20:00:

> **Quote photo (JPG) → POST /audit → 15 seconds → Verdict card with RED/GREEN panel check → Hindi voice note plays → "Copy message to vendor" button works**

That's it. That is your MVP. Every other feature — WhatsApp, Step Functions tracker, second photo, multi-state support — is a nice-to-have.

**Start with this and build outward.**
