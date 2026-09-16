from ocr import extract_text, extract_ocr_token_confidence
from extract_fields import extract_fields
from validator import validate_record
from confidence import calculate_confidence
from lrms import register_document, link_candidate, audit
import re
import os

def _compact(s):
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())

def _area_number(s):
    m = re.search(r"\d+(?:\.\d+)?", str(s or ""))
    return m.group(0) if m else None

def _address_tokens(s):
    # Addresses are often shortened in citizen forms. Compare meaningful
    # tokens rather than requiring identical punctuation or extra details.
    stop = {"the", "near", "old", "bus", "stand", "hno", "no", "door", "address", "karnataka", "india", "sy", "sn"}
    return {x for x in re.findall(r"[a-z0-9]+", str(s or "").lower()) if len(x) > 1 and x not in stop}

def _compare(field, user_value, extracted_value):
    if not user_value:
        return None
    if not extracted_value:
        return {"status": "NEEDS_REVIEW", "citizen": user_value, "extracted": None}

    a = _compact(user_value)
    b = _compact(extracted_value)

    if field == "extent":
        aa, bb = _area_number(user_value), _area_number(extracted_value)
        matched = aa is not None and bb is not None and aa == bb
    elif field == "address":
        ua, eb = _address_tokens(user_value), _address_tokens(extracted_value)
        # A citizen may provide an abbreviated address. It is consistent when
        # all meaningful citizen tokens occur in the extracted address.
        matched = bool(ua) and ua.issubset(eb)
    else:
        matched = a == b

    return {
        "status": "MATCH" if matched else "MISMATCH",
        "citizen": user_value,
        "extracted": extracted_value,
    }

def process_document(image_path, citizen_data=None):
    citizen_data = citizen_data or {}
    text = extract_text(image_path)
    ocr_tokens = [] if os.environ.get("SKIP_OCR_TOKEN_CONFIDENCE", "1") == "1" else extract_ocr_token_confidence(image_path)
    fields, handwriting_evidence = extract_fields(text, image_path)
    validation = validate_record(fields)

    comparisons = {}
    mapping = {
        "owner_name": "owner_name",
        "khata_number": "khata_number",
        "survey_number": "survey_number",
        "village": "village",
        "district": "district",
        "address": "address",
        "extent": "area",
        "land_type": "land_type",
    }
    for extracted_field, citizen_key in mapping.items():
        user_value = citizen_data.get(citizen_key, "")
        extracted_value = fields.get(extracted_field)
        comp = _compare(extracted_field, user_value, extracted_value)
        if comp is not None:
            comparisons[extracted_field] = comp

    confidence = calculate_confidence(fields, validation, comparisons, ocr_tokens)
    # Prototype LRMS linkage: use extracted survey/location/owner evidence to
    # find the historical chain. This does not make a legal ownership decision.
    lrms_link = link_candidate(fields)
    import os
    document_registry = register_document(image_path, os.path.basename(image_path), fields=fields)
    if lrms_link.get("linked"):
        audit("DOCUMENT_LINKED_TO_LRMS_HISTORY", lrms_link.get("best_match",{}).get("record_id"),
              f"survey={fields.get('survey_number')}; match_score={lrms_link.get('match_score',0)}")
    else:
        audit("DOCUMENT_PROCESSED_NO_LRMS_MATCH", None, f"survey={fields.get('survey_number')}")
    if handwriting_evidence:
        # Template-assisted handwriting values are displayed as extracted, but
        # remain review-priority fields because the current engine is not a
        # production handwriting recognizer.
        for field, ev in handwriting_evidence.items():
            if field in confidence:
                confidence[field]["score"] = 70
                confidence[field]["status"] = "NEEDS_REVIEW"
                confidence[field]["components"]["handwriting_mode"] = ev.get("mode")
                confidence[field]["reason"] = "Handwritten legacy form: template-assisted candidate; human verification required"
    return {
        "ocr_text": text,
        "fields": fields,
        "validation": validation,
        "confidence": confidence,
        "comparisons": comparisons,
        "ocr_token_confidence": ocr_tokens,
        "handwriting_evidence": handwriting_evidence,
        "lrms_link": lrms_link,
        "document_registry": document_registry,
    }
