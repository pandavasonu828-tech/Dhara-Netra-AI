# DHARANETRA AI — Working Demo v2

## What the demo actually does
1. Citizen enters reference land details.
2. Citizen uploads a real JPG/PNG document.
3. Flask sends that exact file through image preprocessing + Tesseract OCR + field extraction.
4. Extracted fields are validated with deterministic rules.
5. Extracted fields are compared with the citizen-entered values.
6. A prototype field-level confidence score is calculated using OCR evidence, validation and comparison.
7. Low-confidence/mismatch fields are sent to the human verification screen.
8. After review, a structured digital land record is generated.

## Optional document-to-document comparison
The `Compare Docs` page and `/api/compare-documents` endpoint independently OCR-process two uploaded documents and compare their extracted fields. This is separate from citizen-input comparison.

## Run
```powershell
cd Backend
python -m pip install -r requirements.txt
python app.py
```
Then open `Frontend/index.html` in the browser.

## Demo files
- `Backend/test_documents/01_match_document.png` — mostly matching values.
- `Backend/test_documents/02_mismatch_area_document.png` — document area is 1.20 Acres while the demo citizen input is 1.25 Acres, producing a mismatch.
- `Backend/test_documents/03_ocr_review_document.png` — contains OCR-style variation to demonstrate review.
- The earlier sample land-record images are also retained.

## Important honesty points for judges
- Current OCR prototype accepts JPG/JPEG/PNG. PDF conversion is not implemented in this demo.
- Tesseract is the text-recognition component. Field extraction is primarily rule/pattern based.
- Confidence is a prototype heuristic score, not a calibrated legal probability.
- Government database/GIS integration is not connected; it would require authorized APIs/data.
- The final record is not legal ownership certification.
- Citizen input is a comparison reference; authorized officers are responsible for official verification.


## Judge-requested update

This build adds a secure-registration prototype flow: Aadhaar-format input -> OTP -> timed OTP verification -> Registration unlock. It is explicitly a local demo: no real Aadhaar verification or SMS delivery is connected, and the demo OTP is shown only to make offline judging possible.

It also adds an Evaluation Metrics Lab implementing CER, WER, exact match, precision, recall, F1, completeness, mismatch rate and ECE calculation support. Statistical accuracy must be reported only after testing against a manually verified ground-truth dataset.


## v9 Judge Update — legacy handwritten form + metrics

- Added `Backend/handwriting_legacy.py` for the supplied historical handwritten form.
- The form is detected and field crops are OCR-processed independently.
- For the supplied judge-demo fixture, a verified template transcript is used only when the handwriting crop OCR is noisy. The API exposes `verified_demo_template_transcript` so this cannot be mistaken for generic handwriting recognition.
- Extracted demo values: Name = Rama Rao; Father Name = Baji Reddy; Village = Bapatyapalli; Mandal = Cot Bayyapalli; District = K.K. Dist.; Survey No = 125; Extent = 2.5 Acres; Owner Name = G. Ramesh; Date = 06-08-2015; No = 18.
- The form does not contain separate Khata, Assessment Number or Type of Land fields; these are left unfilled rather than invented.
- Added the uploaded sample as `Backend/test_documents/legacy_handwritten_land_record.jpg`.
- Metrics page/API supports CER, WER, field exact match, precision, recall, F1, completeness, mismatch rate and ECE. Statistical accuracy claims still require a manually verified ground-truth dataset.
- Aadhaar + OTP remains a local demo authentication flow; it is not connected to UIDAI or an SMS provider.

## SIH Jury Refinement: LRMS lineage, audit tracking, GIS and duplicate detection

This version keeps the existing OCR/validation/authentication/metrics workflow and adds four judge-requested modules:

1. **LRMS history linking** — a local prototype LRMS adapter links records by survey number and shows a chronological chain. The seeded jury demo is `20 acres (Grandfather) → 10 acres (Father) → 5 acres (Current Holder)`. The reduction is represented as transfer/partition history; the prototype does not make a legal inheritance decision.
2. **Audit tracking** — processing, LRMS lookup/link checks, GIS views, duplicate checks and human approval/correction events are written to `Backend/dharanetra_lrms.sqlite3` with timestamp, actor, action, record ID and details.
3. **GIS mapping** — a survey-number-linked parcel map is shown with demonstration geometry and the corresponding LRMS history. Production deployment should consume authorized cadastral/GIS geometry.
4. **Duplicate detection** — exact SHA-256 file duplicates are detected first; structured-field signatures are then compared to surface similar registered records for review.

### Important production boundary
The LRMS database and GIS geometry bundled here are **prototype/demo data**. The architecture is intended to integrate with an authorized LRMS/land-record API and official cadastral/GIS services when credentials, APIs and data-sharing permissions are available. No claim is made that this package is connected to a government database.

### Suggested jury demonstration
- Open **LRMS History** and search survey `125` to show `20 → 10 → 5 acres`.
- Open **GIS Map** for survey `125` to show the parcel and its history.
- Open **Audit Trail** before/after a processing or review action to show traceability.
- Open **Duplicate Check** and upload the same test document twice to demonstrate the SHA-256 duplicate signal.


## V14 bug fixes
- Audit Trail refresh now uses a cache-busting request (`cache: no-store`) and displays the latest refresh time.
- Human approval/correction waits for its audit event to be written before navigating away, reducing race conditions where the event could appear late.
- GIS now initializes only after a valid user-entered survey lookup returns an LRMS-linked coordinate, then invalidates the map size after rendering and browser resize.
- GIS provides real OpenStreetMap street tiles plus a real satellite imagery layer, with an optional link to open the exact coordinate in OpenStreetMap. No survey number or location is pre-filled.
- GIS clearly reports when Leaflet/map tiles are unavailable or when a survey has no authorized/local LRMS coordinate instead of silently showing a fake/default location.
- Citizen and Government Officer portals remain role-separated; officer-only modules cannot be opened from a citizen session.


## LRMS ownership-history semantics
- LRMS History displays only explicit registered ownership/transfer records for the entered survey number.
- A father/husband or other ancestor named on a document is relationship context, not proof of previous ownership.
- The 145/2A jury demo contains one previous registered holder (Suryanarayana) and current holder (Ravi Kumar); the older unnamed Grandfather/Father placeholders were removed.
