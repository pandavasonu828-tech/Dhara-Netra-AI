from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os, uuid, time, secrets, hashlib, re
from werkzeug.utils import secure_filename
from pipeline import process_document
from ocr import extract_text, tesseract_status
from extract_fields import extract_fields
from metrics import cer, wer, exact_match, precision_recall_f1, expected_calibration_error
from lrms import search_records, chain, audit_events, audit, gis_parcel, link_candidate, append_record_from_verified, duplicate_candidates, register_document, create_review_case, review_cases, get_review_case, decide_review_case

# Demo authentication state. For production, replace with an authorized identity/OTP provider.
OTP_TTL_SECONDS = 120
MAX_OTP_ATTEMPTS = 5
AUTH_SESSIONS = {}
OTP_CHALLENGES = {}

def _hash_identifier(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def _valid_aadhaar(value):
    return bool(re.fullmatch(r"\d{12}", value or ""))

def _new_token():
    return secrets.token_urlsafe(32)

def _require_auth():
    token = request.headers.get("X-Auth-Token", "")
    session = AUTH_SESSIONS.get(token)
    if not session or session["expires_at"] < time.time():
        if token in AUTH_SESSIONS:
            AUTH_SESSIONS.pop(token, None)
        return None
    return session

app = Flask(__name__)
CORS(app)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.errorhandler(413)
def request_too_large(_exc):
    return jsonify({"status":"error", "message":"The uploaded document is larger than the 10 MB prototype limit."}), 413


@app.errorhandler(500)
def internal_error(exc):
    app.logger.exception("Unhandled server error: %s", exc)
    return jsonify({"status":"error", "message":"The server could not complete document processing. Check the document format and try again."}), 500


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file):
    safe = secure_filename(file.filename)
    filename = f"{uuid.uuid4().hex[:8]}_{safe}"
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)
    return filename, path


@app.route("/")
def home():
    # Serve the actual frontend from the same Render origin so browser API calls
    # using window.location.origin reach this Flask backend.
    frontend_dir = os.path.join(BASE_DIR, "..", "Frontend")
    return send_from_directory(frontend_dir, "index.html")


@app.route("/<path:path>")
def frontend_files(path):
    # Serve frontend assets (for example script.js) from the same Render service.
    # Keep unknown /api/* paths as JSON 404s instead of returning the HTML app.
    if path.startswith("api/"):
        return jsonify({"status": "error", "message": "API endpoint not found."}), 404
    frontend_dir = os.path.join(BASE_DIR, "..", "Frontend")
    requested = os.path.join(frontend_dir, path)
    if os.path.isfile(requested):
        return send_from_directory(frontend_dir, path)
    return send_from_directory(frontend_dir, "index.html")



def _require_role(role):
    session = _require_auth()
    if not session:
        return None
    if session.get("role") != role:
        return None
    return session

@app.route("/api/test")
def test():
    return jsonify({"status": "success", "message": "Dhara-Netra AI backend is reachable", "ocr": tesseract_status()})


@app.route("/health")
def health():
    """Deployment health endpoint for Render and manual diagnostics."""
    ocr = tesseract_status()
    return jsonify({
        "status": "ok" if ocr.get("available") else "degraded",
        "service": "Dhara-Netra AI",
        "ocr": ocr,
    }), (200 if ocr.get("available") else 503)


@app.route("/api/request-otp", methods=["POST"])
def request_otp():
    data = request.get_json(silent=True) or {}
    aadhaar = re.sub(r"\D", "", str(data.get("aadhaar", "")))
    if not _valid_aadhaar(aadhaar):
        return jsonify({"status":"error", "message":"Enter a valid 12-digit Aadhaar number for the demo."}), 400

    challenge_id = _new_token()
    otp = f"{secrets.randbelow(1000000):06d}"
    OTP_CHALLENGES[challenge_id] = {
        "aadhaar_hash": _hash_identifier(aadhaar),
        "otp": otp,
        "created_at": time.time(),
        "expires_at": time.time() + OTP_TTL_SECONDS,
        "attempts": 0,
    }
    # Local demo only: the OTP is returned so the team can demonstrate the flow
    # without connecting a real SMS provider. Never do this in production.
    print(f"[DEMO OTP] Aadhaar ending {aadhaar[-4:]} -> {otp}")
    return jsonify({
        "status":"success",
        "message":"OTP generated for local demo.",
        "challenge_id": challenge_id,
        "expires_in": OTP_TTL_SECONDS,
        "demo_otp": otp,
        "demo_only": True,
    })


@app.route("/api/officer/login", methods=["POST"])
def officer_login():
    data = request.get_json(silent=True) or {}
    employee_id = str(data.get("employee_id", "")).strip()
    password = str(data.get("password", ""))
    if len(employee_id) < 3 or len(password) < 6:
        return jsonify({"status":"error", "message":"Enter an employee ID and a password of at least 6 characters."}), 400
    token = _new_token()
    AUTH_SESSIONS[token] = {
        "role": "officer",
        "employee_id": employee_id,
        "created_at": time.time(),
        "expires_at": time.time() + 60 * 60,
    }
    audit("OFFICER_LOGIN", None, f"employee_id={employee_id}", actor=f"OFFICER:{employee_id}")
    return jsonify({"status":"success", "message":"Officer prototype session created.", "auth_token":token, "role":"officer", "expires_in":3600, "demo_only":True})

@app.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(silent=True) or {}
    challenge_id = str(data.get("challenge_id", ""))
    otp = re.sub(r"\D", "", str(data.get("otp", "")))
    challenge = OTP_CHALLENGES.get(challenge_id)
    if not challenge:
        return jsonify({"status":"error", "message":"OTP session not found. Please request a new OTP."}), 400
    if time.time() > challenge["expires_at"]:
        OTP_CHALLENGES.pop(challenge_id, None)
        return jsonify({"status":"error", "message":"OTP expired. Please request a new OTP."}), 400
    if challenge["attempts"] >= MAX_OTP_ATTEMPTS:
        OTP_CHALLENGES.pop(challenge_id, None)
        return jsonify({"status":"error", "message":"Too many incorrect OTP attempts. Please request a new OTP."}), 429
    challenge["attempts"] += 1
    if otp != challenge["otp"]:
        remaining = MAX_OTP_ATTEMPTS - challenge["attempts"]
        return jsonify({"status":"error", "message":f"Invalid OTP. Please check the 6-digit OTP and try again. {remaining} attempt(s) remaining."}), 401

    token = _new_token()
    AUTH_SESSIONS[token] = {
        "role": "citizen",
        "aadhaar_hash": challenge["aadhaar_hash"],
        "created_at": time.time(),
        "expires_at": time.time() + 60 * 60,
    }
    OTP_CHALLENGES.pop(challenge_id, None)
    return jsonify({"status":"success", "message":"Aadhaar OTP verified successfully.", "auth_token":token, "expires_in":3600})


@app.route("/api/session", methods=["GET"])
def session_info():
    session = _require_auth()
    if not session:
        return jsonify({"status":"error","message":"Not authenticated."}), 401
    return jsonify({"status":"success", "role":session.get("role"), "employee_id":session.get("employee_id")})

@app.route("/api/metrics", methods=["POST"])
def metrics_api():
    """Small evaluation lab: accepts labeled values and returns reproducible metrics."""
    data = request.get_json(silent=True) or {}
    references = data.get("references") or []
    predictions = data.get("predictions") or []
    if references or predictions:
        if len(references) != len(predictions):
            return jsonify({"status":"error", "message":"References and predictions must have the same length."}), 400
        exact = sum(exact_match(r,p) for r,p in zip(references,predictions)) / len(references) if references else 0
        avg_cer = sum(cer(r,p) for r,p in zip(references,predictions)) / len(references) if references else 0
        avg_wer = sum(wer(r,p) for r,p in zip(references,predictions)) / len(references) if references else 0
        return jsonify({"status":"success","mode":"text_evaluation","exact_match":exact,"cer":avg_cer,"wer":avg_wer,"samples":len(references)})
    # Classification metrics. Optional TN is accepted for future extensions,
    # but precision/recall/F1 use TP/FP/FN directly.
    try:
        tp, fp, fn = float(data.get("tp",0)), float(data.get("fp",0)), float(data.get("fn",0))
    except (TypeError, ValueError):
        return jsonify({"status":"error", "message":"TP, FP and FN must be numeric."}), 400

    classification = precision_recall_f1(tp, fp, fn)
    response = {"status":"success","mode":"classification_evaluation","samples":tp+fp+fn,"classification":classification}

    # Confidence calibration: confidence values must be decimals in [0,1] and
    # correctness values must be 0/1 labels from a manually verified dataset.
    confidences = data.get("confidences")
    correctness = data.get("correctness")
    if confidences is not None or correctness is not None:
        if not isinstance(confidences, list) or not isinstance(correctness, list) or len(confidences) != len(correctness):
            return jsonify({"status":"error", "message":"Confidence and correctness arrays must have the same length."}), 400
        try:
            cvals = [max(0.0, min(1.0, float(x))) for x in confidences]
            yvals = [1 if int(x) else 0 for x in correctness]
        except (TypeError, ValueError):
            return jsonify({"status":"error", "message":"Confidence values must be numeric and correctness values must be 0 or 1."}), 400
        response["calibration"] = {"ece": expected_calibration_error(cvals, yvals), "samples": len(cvals)}

    # Completeness and mismatch-rate can be calculated from a runtime comparison.
    extracted = data.get("extracted")
    required = data.get("required")
    comparisons = data.get("comparisons")
    if isinstance(extracted, dict) and isinstance(required, list):
        from metrics import completeness as completeness_metric
        response["completeness"] = completeness_metric(extracted, required)
    if isinstance(comparisons, dict):
        from metrics import mismatch_rate as mismatch_rate_metric
        response["mismatch_rate"] = mismatch_rate_metric(comparisons)

    return jsonify(response)


@app.route("/api/logout", methods=["POST"])
def logout():
    token = request.headers.get("X-Auth-Token", "")
    AUTH_SESSIONS.pop(token, None)
    return jsonify({"status":"success", "message":"Logged out."})


@app.route("/api/process", methods=["POST"])
def process_upload():
    if not _require_auth():
        return jsonify({"status":"error", "message":"Authentication required. Verify Aadhaar OTP before uploading a document."}), 401
    if "document" not in request.files:
        return jsonify({"status": "error", "message": "No document was uploaded."}), 400
    file = request.files["document"]
    if not file.filename:
        return jsonify({"status": "error", "message": "No file selected."}), 400
    if not allowed_file(file.filename):
        return jsonify({"status": "error", "message": "Current OCR prototype accepts JPG, JPEG, PNG or PDF."}), 400

    filename, path = save_upload(file)
    citizen_data = {key: request.form.get(key, "").strip() for key in [
        "owner_name", "khata_number", "survey_number", "village", "district", "address", "area", "land_type"
    ]}
    try:
        result = process_document(path, citizen_data)
        case_id = create_review_case(filename, path, citizen_data, result)
        if case_id:
            result["review_case_id"] = case_id
            result["review_queue_status"] = "PENDING"
        return jsonify({"status": "success", "filename": filename, "message": "Document processed from the uploaded file.", **result})
    except Exception as exc:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
        app.logger.exception("Document processing failed: %s", exc)
        return jsonify({"status": "error", "message": f"Processing failed: {exc}"}), 500


@app.route("/api/process-test-document", methods=["POST"])
def process_test_document():
    """Process one bundled, whitelisted demo image without exposing arbitrary files."""
    if not _require_auth():
        return jsonify({"status":"error", "message":"Authentication required."}), 401
    data = request.get_json(silent=True) or {}
    allowed_demo = {
        "legacy_handwritten_land_record.jpg",
        "01_match_document.png",
        "02_mismatch_area_document.png",
        "03_ocr_review_document.png",
    }
    name = os.path.basename(str(data.get("filename", "")))
    if name not in allowed_demo:
        return jsonify({"status":"error", "message":"Unknown demo document."}), 400
    path = os.path.join(BASE_DIR, "test_documents", name)
    if not os.path.isfile(path):
        return jsonify({"status":"error", "message":"Demo document is missing from the package."}), 404
    citizen_data = data.get("citizen") or {}
    try:
        result = process_document(path, citizen_data)
        return jsonify({"status":"success", "filename":name, "message":"Bundled demo document processed.", **result})
    except Exception as exc:
        return jsonify({"status":"error", "message":f"Processing failed: {exc}"}), 500


@app.route("/api/review-queue", methods=["GET"])
def review_queue_api():
    if not _require_role("officer"):
        return jsonify({"status":"error","message":"Government Officer Portal access required."}),403
    session=_require_auth()
    if not session:
        return jsonify({"status":"error","message":"Authentication required."}),401
    status=str(request.args.get("status","PENDING")).strip().upper()
    rows=review_cases(None if status=='ALL' else status)
    summary={k:len(review_cases(k)) for k in ('PENDING','APPROVED')}
    audit("REVIEW_QUEUE_VIEW",None,f"status={status}; count={len(rows)}",actor=f"OFFICER:{session.get('employee_id','')}")
    return jsonify({"status":"success","cases":rows,"count":len(rows),"summary":summary})

@app.route("/api/review-queue/<case_id>", methods=["GET"])
def review_case_api(case_id):
    if not _require_role("officer"):
        return jsonify({"status":"error","message":"Government Officer Portal access required."}),403
    if not _require_auth():
        return jsonify({"status":"error","message":"Authentication required."}),401
    case=get_review_case(case_id)
    if not case: return jsonify({"status":"error","message":"Review case not found."}),404
    case["document_url"]="/api/uploads/"+case["source_filename"]
    return jsonify({"status":"success","case":case})

@app.route("/api/review-queue/<case_id>/decision", methods=["POST"])
def review_decision_api(case_id):
    session=_require_role("officer")
    if not session: return jsonify({"status":"error","message":"Government Officer Portal access required."}),403
    data=request.get_json(silent=True) or {}
    decision=str(data.get("decision","")).strip().upper()
    if decision not in {"APPROVED","CORRECTED"}:
        return jsonify({"status":"error","message":"Decision must be APPROVED or CORRECTED."}),400
    case=get_review_case(case_id)
    if not case: return jsonify({"status":"error","message":"Review case not found."}),404
    if case.get('status')!='PENDING': return jsonify({"status":"error","message":"This review case has already been decided."}),409
    updated=decide_review_case(case_id,decision,data.get('fields') or {},session.get('employee_id',''),str(data.get('remarks') or ''))
    updated["document_url"]="/api/uploads/"+updated["source_filename"]
    return jsonify({"status":"success","message":"Officer review decision recorded.","case":updated})

@app.route("/api/compare-documents", methods=["POST"])
def compare_documents():
    if not _require_auth():
        return jsonify({"status":"error", "message":"Authentication required. Verify Aadhaar OTP before document comparison."}), 401
    if "document_a" not in request.files or "document_b" not in request.files:
        return jsonify({"status": "error", "message": "Upload both documents for comparison."}), 400
    a, b = request.files["document_a"], request.files["document_b"]
    if not allowed_file(a.filename) or not allowed_file(b.filename):
        return jsonify({"status": "error", "message": "Current comparison prototype accepts JPG, JPEG, PNG or PDF."}), 400
    name_a, path_a = save_upload(a)
    name_b, path_b = save_upload(b)
    try:
        fields_a, _ = extract_fields(extract_text(path_a), path_a)
        fields_b, _ = extract_fields(extract_text(path_b), path_b)
        keys = sorted(set(fields_a) | set(fields_b))
        differences = []
        comparison = {}
        import re
        def compact(v):
            return "".join(ch for ch in str(v or "").lower() if ch.isalnum())
        def area(v):
            m = re.search(r"\d+(?:\.\d+)?", str(v or ""))
            return m.group(0) if m else None
        def address_tokens(v):
            stop = {"the","near","old","bus","stand","hno","no","door","address","india","sy","sn"}
            return {x for x in re.findall(r"[a-z0-9]+", str(v or "").lower()) if len(x)>1 and x not in stop}
        for k in keys:
            va, vb = fields_a.get(k), fields_b.get(k)
            if not va and not vb:
                status = "NOT_PRESENT"
            elif not va or not vb:
                status = "NEEDS_REVIEW"
            elif k == "extent":
                status = "MATCH" if area(va) and area(va) == area(vb) else "MISMATCH"
            elif k == "address":
                aa, bb = address_tokens(va), address_tokens(vb)
                status = "MATCH" if aa and (aa.issubset(bb) or bb.issubset(aa)) else "MISMATCH"
            else:
                status = "MATCH" if compact(va) == compact(vb) else "MISMATCH"
            comparison[k] = {"a": va, "b": vb, "status": status}
            if status in {"MISMATCH", "NEEDS_REVIEW"}:
                differences.append(k)
        return jsonify({"status":"success","document_a":name_a,"document_b":name_b,"fields_a":fields_a,"fields_b":fields_b,"comparison":comparison,"difference_count":len(differences),"differences":differences})
    except Exception as exc:
        return jsonify({"status":"error","message":f"Comparison failed: {exc}"}),500



@app.route("/api/lrms/search", methods=["GET"])
def lrms_search():
    if not _require_role("officer"):
        return jsonify({"status":"error","message":"Government Officer Portal access required."}), 403
    if not _require_auth():
        return jsonify({"status":"error","message":"Authentication required."}), 401
    survey = str(request.args.get("survey_number", "")).strip()
    owner = str(request.args.get("owner_name", "")).strip()
    rows = search_records(survey_number=survey, owner_name=owner)
    current = next((r for r in reversed(rows) if r.get('status') == 'CURRENT'), (rows[-1] if rows else None))
    previous = [r for r in rows if not current or r.get('record_id') != current.get('record_id')]
    audit("LRMS_SEARCH", None, f"survey={survey}; owner={owner}", actor=f"OFFICER:{_require_auth().get('employee_id','')}")
    return jsonify({"status":"success","records":rows,"count":len(rows),"current_holder":current,"previous_records":previous,"history_scope":"all registered LRMS records for the exact survey number"})

@app.route("/api/lrms/link", methods=["POST"])
def lrms_link():
    if not _require_role("officer"):
        return jsonify({"status":"error","message":"Government Officer Portal access required."}), 403
    if not _require_auth():
        return jsonify({"status":"error","message":"Authentication required."}), 401
    data=request.get_json(silent=True) or {}
    fields=data.get("fields") or {}
    result=link_candidate(fields)
    audit("LRMS_LINK_CHECK", result.get("best_match",{}).get("record_id"), f"survey={fields.get('survey_number')}; owner={fields.get('owner_name')}; score={result.get('match_score',0)}", actor=f"OFFICER:{_require_auth().get('employee_id','')}")
    return jsonify({"status":"success", **result})

@app.route("/api/lrms/create", methods=["POST"])
def lrms_create():
    if not _require_role("officer"):
        return jsonify({"status":"error","message":"Government Officer Portal access required."}), 403
    if not _require_auth():
        return jsonify({"status":"error","message":"Authentication required."}), 401
    data=request.get_json(silent=True) or {}
    fields=data.get("fields") or {}
    try:
        rec_id=append_record_from_verified(fields, data.get("transaction_type") or "Verified Update")
        return jsonify({"status":"success","record_id":rec_id})
    except Exception as exc:
        return jsonify({"status":"error","message":str(exc)}),400

@app.route("/api/audit/event", methods=["POST"])
def audit_event_api():
    session=_require_auth()
    if not session:
        return jsonify({"status":"error","message":"Authentication required."}), 401
    data=request.get_json(silent=True) or {}
    actor=(f"OFFICER:{session.get('employee_id')}" if session.get('role')=='officer' else "CITIZEN")
    audit(str(data.get("action") or "UNKNOWN_ACTION"), data.get("record_id"), str(data.get("details") or ""), actor=actor)
    return jsonify({"status":"success"})

@app.route("/api/audit", methods=["GET"])
def audit_api():
    if not _require_role("officer"):
        return jsonify({"status":"error","message":"Government Officer Portal access required."}), 403
    if not _require_auth():
        return jsonify({"status":"error","message":"Authentication required."}), 401
    return jsonify({"status":"success","events":audit_events(int(request.args.get("limit",100)))})

@app.route("/api/gis/parcel", methods=["GET"])
def gis_api():
    if not _require_role("officer"):
        return jsonify({"status":"error","message":"Government Officer Portal access required."}), 403
    if not _require_auth():
        return jsonify({"status":"error","message":"Authentication required."}), 401
    survey=str(request.args.get("survey_number", "")).strip()
    if not survey:
        return jsonify({"status":"error","message":"Enter a survey number from the LRMS record."}),400
    data=gis_parcel(survey)
    audit("GIS_PARCEL_VIEW", None, f"survey={survey}", actor=f"OFFICER:{_require_auth().get('employee_id','')}")
    return jsonify({"status":"success", **data})

@app.route("/api/duplicate-check", methods=["POST"])
def duplicate_check_api():
    if not _require_role("officer"):
        return jsonify({"status":"error","message":"Government Officer Portal access required."}), 403
    if not _require_auth():
        return jsonify({"status":"error","message":"Authentication required."}),401
    if "document" not in request.files:
        return jsonify({"status":"error","message":"Upload a document."}),400
    f=request.files["document"]
    if not allowed_file(f.filename):
        return jsonify({"status":"error","message":"Current duplicate prototype accepts JPG, JPEG, PNG or PDF."}),400
    name,path=save_upload(f)
    fields,_=extract_fields(extract_text(path),path)
    reg,candidates=duplicate_candidates(path,fields)
    audit("DUPLICATE_CHECK", None, f"file={name}; exact_duplicate={reg['exact_duplicate']}; candidates={len(candidates)}", actor=f"OFFICER:{_require_auth().get('employee_id','')}" )
    return jsonify({"status":"success","filename":name,"fields":fields,"registry":reg,"candidates":candidates})

@app.route("/api/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)



if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"DHARANETRA AI backend running on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
