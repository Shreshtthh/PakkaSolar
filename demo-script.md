# PakkaSolar: 3-Minute Hackathon Demo Video Script
**Track 03: Waste and Energy (Rooftop Solar) · Bharat Builds Tour 2026**  
*Format: 180 Seconds (3:00) · Delivery Pace: ~135 WPM (~415 Words Total)*

---

## Storyboard & Timing Overview

| Scene | Timecode | Duration | Story Arc & Core Focus | Word Count |
|---|---|---|---|---|
| **Scene 1** | `0:00 – 0:50` | 50s | **The Human Trap & The Unreadable PDF** (Hamirpur family, barcode rejection, ripple effect, 300-page ALMM PDF) | 114 words |
| **Scene 2** | `0:50 – 1:35` | 45s | **Live Product Demo** (Quote upload, Bedrock parsing, RED verdict, Polly Hindi audio, WhatsApp dealer script) | 104 words |
| **Scene 3** | `1:35 – 2:15` | 40s | **AWS Architecture & Decoupling** (SQS buffer, Perception vs. Judgment: Bedrock vs. DynamoDB, NASA POWER) | 92 words |
| **Scene 4** | `2:15 – 2:45` | 30s | **The ₹75,000 Crore Macro Reality** (Solar is 9% of coal, ₹75k Cr outlay, 60+ tests, < ₹0.85/audit) | 70 words |
| **Scene 5** | `2:45 – 3:00` | 15s | **Closing Call to Action** (Trust unlocks clean energy, open-source repo) | 36 words |
| **Total** | `0:00 – 3:00` | **180s** | **Complete Rubric & Story Arc** | **416 words** |

---

## Second-by-Second Production Script

### Scene 1: The Human Trap & The Unreadable PDF
**Duration:** `0:00 – 0:50` (50 seconds) · **Word Count:** 114 words  
**Core Purpose:** Hook the judges emotionally with a grounded Indian story, expose the information asymmetry, and introduce PakkaSolar's core mission.

- **[Visual / Screen Action]:**  
  - `0:00 - 0:15`: Fullscreen camera shot of speaker speaking with earnest, grounded energy. Show b-roll or stock image of a modest residential home with solar panels.
  - `0:15 - 0:28`: Cut to an image of a DISCOM electricity board inspector scanning a barcode on the back of a solar panel. Red stamp slams down: **"SUBSIDY REJECTED: NON-DCR"**.
  - `0:28 - 0:38`: Split screen: WhatsApp chat showing messages: *"Solar is a scam. Don't install it."*
  - `0:38 - 0:50`: Dramatic switch to screen recording: Scroll rapidly through the official **300+ page, dense, technical MNRE ALMM PDF**. Zoom in on impenetrable tables with model codes like `ASPL-380-HM72`.

- **[Voiceover Script]:**  
  > *"Imagine a middle-class father in Hamirpur earning ₹40,000 a month. He empties his family savings to install rooftop solar, counting on the promised ₹85,800 PM Surya Ghar subsidy.*  
  > *Three months later, the DISCOM inspector climbs onto his roof, scans the panel barcode, and says:* **‘These are cheap imported panels, not on the approved DCR list. Subsidy rejected.’**  
  > *The vendor is gone. The family loses ₹85,800. Devastated, he warns his neighbors and WhatsApp groups: ‘Solar is a scam.’ An entire community stops adopting clean energy.*  
  > *Why did this happen? Because the government publishes its approved list as an unreadable, 300-page technical PDF. No citizen can navigate this. The bottleneck to India’s solar transition isn’t sunlight—it’s trust."*

- **[On-Screen Graphic / Text Overlay]:**  
  - `0:05`: `Hamirpur, HP: ₹40,000/mo Salary · ₹85,800 Subsidy at Risk`
  - `0:22`: `Surprise Rejection: Inspection Happens WEEKS After Payment`
  - `0:32`: `The Ripple Effect: Community Solar Adoption Freezes`
  - `0:42`: `The Reality: 300+ Page Unreadable Government ALMM PDF`
  - `0:48`: `The Bottleneck Isn't Sunlight. It's Trust.`

---

### Scene 2: Live Product Demo (Web App)
**Duration:** `0:50 – 1:35` (45 seconds) · **Word Count:** 104 words  
**Core Purpose:** Show how PakkaSolar solves this instantly in the browser with AI perception, deterministic checking, Hindi voice, and negotiation tools.

- **[Visual / Screen Action]:**  
  - `0:50 - 1:02`: Cut to PakkaSolar web app (`localhost:5173`). Drag and drop a real quotation photo (`quote_fail.jpg`). Animate loading status: *Analyzing Quote $\rightarrow$ Checking ALMM $\rightarrow$ Verifying DISCOM Vendor*.
  - `1:02 - 1:15`: Instant transition to the **RED Verdict Card**. Zoom in on the clear breakdown: `Panels: Waaree WS-540 (ALMM Listed ✅)`, `Vendor: Unregistered Dealer (DISCOM Empanelled ❌)`. Display subsidy warning: **₹85,800 At Risk**.
  - `1:15 - 1:25`: Click **"Play Hindi Voice Note"**. Waveform pulses on screen while Amazon Polly’s crisp Neural voice plays aloud.
  - `1:25 - 1:35`: Click **"Copy Message for Vendor"**. Show popover with ready-to-paste WhatsApp text demanding a compliant empanelled quote.

- **[Voiceover Script]:**  
  > *"PakkaSolar puts that 300-page PDF into an intelligent AWS auditor in your pocket.*  
  > *Watch this: A homeowner uploads a photo of their dealer's quote. In seconds, PakkaSolar returns an unambiguous verdict.*  
  > *In this audit, while the panels are valid, the dealer is NOT empanelled with the state electricity board. The audit flags RED—saving ₹85,800 before a single rupee changes hands.*  
  > *For accessibility, Amazon Polly generates a clear Hindi voice note explaining the risk in plain words.*  
  > *And with one click, PakkaSolar generates a pre-written WhatsApp negotiation message to demand a verified contract from the vendor."*

- **[Polly Audio Excerpt (Underneath VO at 1:20)]:**  
  > *(Subtle background audio)*: *"Namaste! Aapke quote ka vendor empanelled nahi hai. Turant naya quote maangein..."*

- **[On-Screen Graphic / Text Overlay]:**  
  - `0:55`: `Amazon Bedrock Multimodal OCR`
  - `1:06`: `Verdict: 🔴 HIGH RISK (Unregistered Vendor)`
  - `1:18`: `Amazon Polly Neural (Hindi Voice Note)`
  - `1:28`: `1-Click WhatsApp Vendor Negotiation Script`

---

### Scene 3: AWS Architecture & Why AWS
**Duration:** `1:35 – 2:15` (40 seconds) · **Word Count:** 92 words  
**Core Purpose:** Prove architectural depth. Explain why LLMs alone fail compliance and how AWS SAM delivers a decoupled, hallucination-free pipeline.

- **[Visual / Screen Action]:**  
  - `1:35 - 1:52`: Fullscreen animated Mermaid architecture diagram highlighting the serverless flow: `API Gateway → Lambda → S3 → SQS Queue → audit_worker Lambda`.
  - `1:52 - 2:05`: Split screen. Left: Bedrock Nova Pro JSON schema output. Right: DynamoDB table with 3,914 MNRE ALMM models and partition key lookups.
  - `2:05 - 2:15`: Highlight NASA POWER integration badge. Show solar insolation formula: $GHI \times PR(0.80) \times CEA(0.716\text{ kg CO}_2\text{/kWh})$.

- **[Voiceover Script]:**  
  > *"Behind the scenes, PakkaSolar runs on an event-driven AWS serverless architecture deployed via SAM.*  
  > *API Gateway acknowledges uploads in milliseconds, while Amazon SQS buffers heavy AI processing to guarantee zero dropped webhooks.*  
  > *Our core design principle is: **The LLM perceives; it never judges**.*  
  > *Amazon Bedrock Nova extracts messy handwritten text into validated schemas. But the audit is 100% deterministic, verifying against 3,914 official MNRE models and DISCOM vendor tables in Amazon DynamoDB.*  
  > *We then calculate realistic solar generation using satellite climatology from NASA POWER on the AWS Open Data Registry."*

- **[On-Screen Graphic / Text Overlay]:**  
  - `1:40`: `Decoupled Architecture: Amazon SQS Buffer + DLQ`
  - `1:50`: `Architectural Principle: LLM Perceives, DynamoDB Decides`
  - `1:58`: `3,914 Official ALMM Models Verified in DynamoDB`
  - `2:08`: `NASA POWER: Physics-Based Satellite Solar Yield`

---

### Scene 4: The ₹75,000 Crore Macro Reality & Rigor
**Duration:** `2:15 – 2:45` (30 seconds) · **Word Count:** 70 words  
**Core Purpose:** Connect the project to national macro impact (coal vs. solar) and showcase engineering rigor with 60+ passing tests and < ₹0.85 unit cost.

- **[Visual / Screen Action]:**  
  - `2:15 - 2:28`: High-impact infographic: Coal accounts for ~75% of India’s electricity; Solar is only ~7% (less than 10% of coal). Overlay banner: **PM Surya Ghar: ₹75,021 Crore ($9B Outlay)**.
  - `2:28 - 2:45`: Fast terminal recording running `pytest tests/ -v`. Show 60+ unit, logic, and Moto integration tests passing in green. Display cost card: `< ₹0.85 per audit`.

- **[Voiceover Script]:**  
  > *"Why does this matter? Right now, solar produces less than 10% of what coal generates in India. The government committed ₹75,000 Crores to fix that ratio—but that capital won't deploy if families are terrified of subsidy fraud.*  
  > *We built a production-grade system to fix this.*  
  > *Our codebase includes over 60 automated tests using Moto and Pytest, running completely offline.*  
  > *And with serverless Lambda and DynamoDB, an audit costs less than 85 paise."*

- **[On-Screen Graphic / Text Overlay]:**  
  - `2:18`: `Macro Reality: Solar is Only ~9% of Coal Generation in India`
  - `2:24`: `PM Surya Ghar Outlay: ₹75,021 Crore ($9 Billion)`
  - `2:32`: `60+ Automated Tests Passing (Pytest + Moto Mocks)`
  - `2:40`: `Cost Per Audit: < ₹0.85 (Fractions of a Rupee)`

---

### Scene 5: Closing Vision & Submission
**Duration:** `2:45 – 3:00` (15 seconds) · **Word Count:** 36 words  
**Core Purpose:** Memorable send-off, repo link, track alignment, high energy.

- **[Visual / Screen Action]:**  
  - `2:45 - 2:55`: Split view of the open-source GitHub repo (`PakkaSolar`), clean README badges, and the live application.
  - `2:55 - 3:00`: Camera shot of speaker. Closing lower-third: Name, NIT Hamirpur, Track 03: Waste and Energy.

- **[Voiceover Script]:**  
  > *"India targets 10 million solar rooftops by 2027. By taking complex government regulations and putting a trusted auditor in every citizen's pocket, PakkaSolar makes rooftop solar truly pakka.*  
  > *Check our open-source repo. Check before you sign. Thank you!"*

- **[On-Screen Graphic / Text Overlay]:**  
  - `2:47`: `Bharat Builds Tour · Track 03: Waste and Energy`
  - `2:52`: `github.com/your-org/PakkaSolar`
  - `2:57`: `PakkaSolar — Check Before You Sign ☀️`

---

## Technical Appendix: WhatsApp Implementation Status

> **Self-Disclosure for Evaluators & Q&A:**  
> - **Deployed in SAM:** The API Gateway webhook routing (`GET /webhook/wa`, `POST /webhook/wa`) and the cryptographic Meta verification handshake (`hub.challenge`) are implemented in `webhook_handler/lambda_function.py`.  
> - **Current Demo Experience:** Users interact via the responsive web application (`localhost:5173`), which includes the instant **1-click WhatsApp counter-offer script copy** feature for dealers.  
> - **Roadmap Integration:** Connecting outbound media via Meta Cloud API / AWS End User Messaging Social requires ~2 hours of credential provisioning and is slated for Phase 2.
