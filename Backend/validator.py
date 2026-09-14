import re
from datetime import datetime


def result(status, message, checks=None):
    return {"status": status, "message": message, "checks": checks or []}


def validate_record(fields):
    validation = {}

    # Presence checks
    required = [
        "district", "mandal", "village", "survey_number", "extent",
        "land_type", "owner_name", "document_number"
    ]
    for field in required:
        if not fields.get(field):
            validation[field] = result("NEEDS_REVIEW", "Information is missing", ["presence_failed"])
        else:
            validation[field] = result("VALID", "Information is present", ["presence_passed"])

    # Survey number format
    v = fields.get("survey_number")
    if v:
        ok = bool(re.fullmatch(r"\d+(?:/[0-9A-Za-z]+)+", v.strip()))
        validation["survey_number"] = result(
            "VALID" if ok else "NEEDS_REVIEW",
            "Survey number format is valid" if ok else "Survey number format needs review",
            ["presence_passed", "survey_format_passed" if ok else "survey_format_failed"]
        )

    # Extent sanity
    v = fields.get("extent")
    if v:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", v)
        ok = bool(m) and float(m.group(1)) > 0
        validation["extent"] = result(
            "VALID" if ok else "NEEDS_REVIEW",
            "Land area is valid" if ok else "Land area needs review",
            ["presence_passed", "positive_area_passed" if ok else "area_check_failed"]
        )

    # Land type
    v = fields.get("land_type")
    allowed = {"agricultural", "residential", "commercial", "industrial"}
    ok = bool(v) and v.lower() in allowed
    validation["land_type"] = result(
        "VALID" if ok else "NEEDS_REVIEW",
        "Land type is recognized" if ok else "Land type needs review",
        ["presence_passed", "land_type_passed" if ok else "land_type_failed"]
    ) if v else result("NEEDS_REVIEW", "Information is missing", ["presence_failed"])

    # Assessment number
    v = fields.get("assessment_number")
    if v:
        ok = bool(re.fullmatch(r"(?:AS-\d{4}-\d+|\d{2}-\d{3}-\d{3})", v.strip(), re.I))
        validation["assessment_number"] = result("VALID" if ok else "NEEDS_REVIEW", "Assessment number format is valid" if ok else "Assessment number needs review", ["presence_passed", "assessment_format_passed" if ok else "assessment_format_failed"])
    else:
        validation["assessment_number"] = result("NEEDS_REVIEW", "Information is missing", ["presence_failed"])

    # Person/location fields: presence + simple sanity checks.
    for field in ["district", "mandal", "village", "owner_name", "father_husband_name", "address"]:
        v = fields.get(field)
        if not v:
            validation[field] = result("NEEDS_REVIEW", "Information is missing", ["presence_failed"])
        else:
            # Reject values that look like another label or are implausibly short.
            bad = len(v) < 2 or bool(re.search(r"^(District|Mandal|Village|Owner Name|Address)$", v, re.I))
            validation[field] = result("NEEDS_REVIEW" if bad else "VALID", "Value needs review" if bad else "Information is present and readable", ["presence_passed", "sanity_failed" if bad else "sanity_passed"])

    # Document number
    v = fields.get("document_number")
    if v:
        ok = bool(re.fullmatch(r"(?:[A-Z]{1,3}-\d{4}-\d+|\d{1,8})", v.strip(), re.I))
        validation["document_number"] = result("VALID" if ok else "NEEDS_REVIEW", "Document number format is valid" if ok else "Invalid document number format", ["presence_passed", "document_format_passed" if ok else "document_format_failed"])

    # Date
    v = fields.get("date")
    if v:
        parsed = False
        for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
            try:
                datetime.strptime(v.strip(), fmt)
                parsed = True
                break
            except ValueError:
                pass
        validation["date"] = result(
            "VALID" if parsed else "NEEDS_REVIEW",
            "Date is valid" if parsed else "Invalid date",
            ["presence_passed", "date_format_passed" if parsed else "date_format_failed"]
        )
    else:
        validation["date"] = result("NEEDS_REVIEW", "Date is missing", ["presence_failed"])

    field_results = {k: v for k, v in validation.items()}
    valid_count = sum(v["status"] == "VALID" for v in field_results.values())
    total = len(field_results)
    review_count = total - valid_count
    validation["summary"] = {
        "status": "VALID" if review_count == 0 else "NEEDS_REVIEW",
        "message": "All extracted fields passed rule-based validation" if review_count == 0 else f"{review_count} field(s) need human review",
        "total_fields": total,
        "valid_fields": valid_count,
        "review_fields": review_count,
    }
    return validation
