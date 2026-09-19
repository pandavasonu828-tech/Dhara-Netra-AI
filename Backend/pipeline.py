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
    stop = {
        "the",
        "near",
        "old",
        "bus",
        "stand",
        "hno",
        "no",
        "door",
        "address",
        "karnataka",
        "india",
        "sy",
        "sn",
    }

    return {
        x
        for x in re.findall(
            r"[a-z0-9]+",
            str(s or "").lower()
        )
        if len(x) > 1 and x not in stop
    }


def _compare(field, user_value, extracted_value):
    if not user_value:
        return None

    if not extracted_value:
        return {
            "status": "NEEDS_REVIEW",
            "citizen": user_value,
            "extracted": None,
        }

    a = _compact(user_value)
    b = _compact(extracted_value)

    if field == "extent":

        aa = _area_number(user_value)
        bb = _area_number(extracted_value)

        matched = (
            aa is not None
            and bb is not None
            and aa == bb
        )

    elif field == "address":

        ua = _address_tokens(user_value)
        eb = _address_tokens(extracted_value)

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

    # =========================================================
    # 1. MAIN OCR
    # =========================================================

    text = ""
    ocr_error = None

    try:

        text = extract_text(image_path)

        print(
            f"[OCR SUCCESS] Extracted {len(text)} characters",
            flush=True,
        )

    except Exception as exc:

        text = ""

        ocr_error = (
            f"{type(exc).__name__}: {exc}"
        )

        print(
            f"[OCR ERROR] {ocr_error}",
            flush=True,
        )

    # =========================================================
    # 2. OCR TOKEN CONFIDENCE
    # =========================================================

    # This is a second OCR-related operation.
    # It is disabled by default on Render.
    #
    # Therefore the main OCR pass is not followed by
    # another expensive OCR operation.

    ocr_tokens = []

    if os.environ.get(
        "SKIP_OCR_TOKEN_CONFIDENCE",
        "1"
    ) != "1":

        try:

            ocr_tokens = extract_ocr_token_confidence(
                image_path
            )

            print(
                f"[OCR TOKEN SUCCESS] "
                f"{len(ocr_tokens)} tokens",
                flush=True,
            )

        except Exception as exc:

            print(
                f"[OCR TOKEN ERROR] "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

            ocr_tokens = []

    # =========================================================
    # 3. FIELD EXTRACTION
    # =========================================================

    try:

        fields, handwriting_evidence = extract_fields(
            text,
            image_path,
        )

    except Exception as exc:

        print(
            f"[FIELD EXTRACTION ERROR] "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

        fields = {}
        handwriting_evidence = {}

    # =========================================================
    # 4. VALIDATION
    # =========================================================

    try:

        validation = validate_record(fields)

    except Exception as exc:

        print(
            f"[VALIDATION ERROR] "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

        validation = {}

    # =========================================================
    # 5. CITIZEN DATA VS OCR DATA
    # =========================================================

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

        user_value = citizen_data.get(
            citizen_key,
            "",
        )

        extracted_value = fields.get(
            extracted_field
        )

        comp = _compare(
            extracted_field,
            user_value,
            extracted_value,
        )

        if comp is not None:
            comparisons[extracted_field] = comp

    # =========================================================
    # 6. CONFIDENCE
    # =========================================================

    try:

        confidence = calculate_confidence(
            fields,
            validation,
            comparisons,
            ocr_tokens,
        )

    except Exception as exc:

        print(
            f"[CONFIDENCE ERROR] "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

        confidence = {}

    # =========================================================
    # 7. LRMS LINK
    # =========================================================

    try:

        lrms_link = link_candidate(fields)

    except Exception as exc:

        print(
            f"[LRMS LINK ERROR] "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

        lrms_link = {
            "linked": False,
            "error": str(exc),
        }

    # =========================================================
    # 8. DOCUMENT REGISTRY
    # =========================================================

    try:

        document_registry = register_document(
            image_path,
            os.path.basename(image_path),
            fields=fields,
        )

    except Exception as exc:

        print(
            f"[DOCUMENT REGISTRY ERROR] "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

        document_registry = {
            "registered": False,
            "error": str(exc),
        }

    # =========================================================
    # 9. AUDIT
    # =========================================================

    try:

        if lrms_link.get("linked"):

            audit(
                "DOCUMENT_LINKED_TO_LRMS_HISTORY",
                lrms_link.get(
                    "best_match",
                    {},
                ).get("record_id"),
                (
                    f"survey="
                    f"{fields.get('survey_number')}; "
                    f"match_score="
                    f"{lrms_link.get('match_score', 0)}"
                ),
            )

        else:

            audit(
                "DOCUMENT_PROCESSED_NO_LRMS_MATCH",
                None,
                (
                    f"survey="
                    f"{fields.get('survey_number')}"
                ),
            )

    except Exception as exc:

        print(
            f"[AUDIT ERROR] "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

    # =========================================================
    # 10. HANDWRITING EVIDENCE
    # =========================================================

    if handwriting_evidence:

        for field, ev in handwriting_evidence.items():

            if field in confidence:

                confidence[field]["score"] = 70

                confidence[field]["status"] = (
                    "NEEDS_REVIEW"
                )

                confidence[field]["components"][
                    "handwriting_mode"
                ] = ev.get("mode")

                confidence[field]["reason"] = (
                    "Handwritten legacy form: "
                    "template-assisted candidate; "
                    "human verification required"
                )

    # =========================================================
    # 11. FINAL STATUS
    # =========================================================

    if ocr_error:

        processing_status = "NEEDS_REVIEW"
        ocr_status = "FAILED_SAFE"

    else:

        processing_status = "PROCESSED"
        ocr_status = "COMPLETED"

    # =========================================================
    # 12. RETURN RESULT
    # =========================================================

    return {

        "processing_status": processing_status,

        "ocr_status": ocr_status,

        "ocr_error": ocr_error,

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