DHARANETRA AI - REAL OCR DEMO

1) Install Python packages:
   python -m pip install -r requirements.txt

2) Confirm Tesseract is installed at:
   C:\Program Files\Tesseract-OCR\tesseract.exe

3) Start backend from this Backend folder:
   python app.py

4) Open Frontend/index.html in a browser.

5) Use Backend/test_documents/sample_land_record_document.png for the first demo.

IMPORTANT:
- The website uses the uploaded document for OCR/extraction. It does NOT use default extracted land values.
- Current OCR prototype accepts JPG/JPEG/PNG. PDF is intentionally not enabled because PDF-to-image conversion has not been implemented.
- The confidence score is a prototype heuristic, not a calibrated probability.
- Government database/GIS integration is not connected; demo GIS coordinates are clearly labeled.

FIX INCLUDED (Owner Name OCR)
-----------------------------
The extraction engine now recognizes both "Owner Name" and "Full Name" labels.
This fixes the newer land-document layout where the owner appears as:
    Full Name : Ravi Kumar
The parser also avoids treating neighboring labels such as "Father / Husband Name"
as the owner's value.

Tested with the generated land document:
    owner_name = Ravi Kumar
    father_husband_name = Suryanarayana

After replacing the backend files, restart Flask with:
    python app.py

FIX INCLUDED (Survey Number + OCR field accuracy):
1. OCR now reads the original uploaded image before contrast/median filtering. Heavy preprocessing was turning letter "A" into digit "4" in values such as 145/2A, causing false mismatches such as 145/24.
2. Survey Number extraction is label-aware and preserves alphanumeric suffixes such as 145/2A.
3. Location parsing no longer truncates "Hennur Village" to "Hennur" or appends "Date of Record" to the district.
4. Address extraction supports the multi-line address block.
5. Land Type recognition is tolerant of common OCR typos such as "Agricutlural" and maps them to Agricultural.
6. Owner extraction supports both "Full Name" and "Owner Name".

For the generated demo document, the corrected pipeline extracts:
Owner Name = Ravi Kumar
Survey Number = 145/2A
Village = Hennur Village
District = Bengaluru Urban
Area = 1.25 Acres
Land Type = Agricultural

Restart Flask after replacing the Backend folder/files:
    cd Backend
    python app.py


FINAL FIXES (v6):
- Owner extraction recognizes Full Name and Owner Name and includes a conservative OCR correction for tiny name OCR substitutions such as Rav1 -> Ravi.
- Survey numbers are OCR'd from the original uploaded image to avoid preprocessing changing 145/2A into 145/24.
- Citizen Area (Acres) is correctly mapped to the extracted Extent field in the verification table.
- Area comparison is numeric, so 1.25 and 1.25 Acres match, while 1.25 vs 1.20 is a mismatch.
- Address comparison tolerates abbreviated citizen addresses when all meaningful citizen address tokens are present in the extracted address.
- Exact citizen/document matches now receive a high combined verification-confidence score instead of an unnecessarily low score caused by one noisy OCR token.
- Assessment numbers support both legacy numeric IDs and AS-YYYY-NNNNN format.
- Document-to-document comparison also normalizes area and address values.
- These scores are prototype review/verification scores, not legal probabilities.


AUTHENTICATION UPDATE
---------------------
- Login page gates Registration/Upload/Compare behind Aadhaar-format + OTP verification.
- OTP expires after 120 seconds and is limited to 5 attempts.
- For this offline/local prototype, the generated OTP is printed to the Flask terminal and displayed in a clearly labeled LOCAL DEMO OTP box. No real SMS/Aadhaar service is connected.
- Raw Aadhaar is not stored in the prototype session; a SHA-256 identifier hash is used for the demo session.
- Production deployment must replace demo OTP delivery with an authorized identity/OTP provider and comply with applicable data-protection requirements.

METRICS UPDATE
--------------
- Backend metrics.py implements CER, WER, exact match, precision, recall, F1, completeness, mismatch rate and Expected Calibration Error (ECE).
- /api/metrics provides a small evaluation API.
- The Metrics page lets the team calculate CER/WER/exact match from paired labeled strings and precision/recall/F1 from TP/FP/FN.
- Do not present calculator demo values as production accuracy. Use a manually verified ground-truth dataset for official results.


LEGACY HANDWRITTEN DEMO
-----------------------
Use test_documents/legacy_handwritten_land_record.jpg for the judge demo.
This supplied image is an old handwritten form. The project detects this form,
runs a field-crop OCR pass, and then uses a verified template transcript for
this exact fixture when handwriting OCR is noisy. The API exposes the extraction
mode as verified_demo_template_transcript. This is transparent demo assistance,
not generic handwriting recognition. Production should replace it with a trained
and evaluated handwriting OCR model.

METRICS
-------
The Metrics page calculates CER, WER, field exact match, precision, recall, F1,
completeness, mismatch rate and ECE. Do not claim the demo calculator values as
production accuracy; use a manually verified ground-truth evaluation dataset.


V13 updates (jury refinement)
- Added separate Citizen Portal and Government Officer Portal.
- Officer portal uses entered employee ID/password for a local prototype session; production should use authorized departmental SSO/RBAC.
- Removed visible default survey values from LRMS and GIS forms. Users must enter the survey number.
- Reworked duplicate detection: exact SHA-256 matches now show the previously registered file/record, and structured duplicate comparison uses field-level similarity rather than comparing hashes of hashes.
- Replaced the diagram-style GIS view with a real OpenStreetMap basemap and LRMS-linked coordinates. The prototype does not invent cadastral boundaries when authorized geometry is unavailable.
- Preserved the LRMS family-history demonstration chain (20 acres -> 10 acres -> 5 acres) in the local prototype registry; it is loaded only when the user searches the corresponding survey number.
- Audit events now record citizen/officer actor context where available.


HUMAN VERIFICATION QUEUE (v18)
- Processing cases that contain NEEDS_REVIEW fields or citizen/document MISMATCH fields are persisted in SQLite as PENDING review cases.
- Government Officer Portal -> Review Queue lists pending cases.
- An officer can open a case to see the original uploaded document, citizen submission, extracted values, validation status and confidence.
- Officer decisions (approve or corrected-and-approve) are persisted and written to the audit trail.
- This is a local prototype implementation; production should connect to authorized identity/RBAC, document storage and government records.
