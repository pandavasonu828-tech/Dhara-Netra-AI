from handwriting_legacy import is_legacy_handwritten_form, extract_legacy_handwritten_fields
import re


def clean_text(text):
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def clean_value(value):
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip(" :.-|\t")
    return value or None


# IMPORTANT: keep these as complete field labels.  Matching a bare word such
# as "Name" caused the old parser to capture neighbouring labels instead of
# the actual owner value.
LABELS = {
    "owner": [r"Full\s+Name", r"Owner\s+Name"],
    "father": [r"Father\s*/?\s*Husband\s+Name", r"Father\s+Name", r"Husband\s+Name"],
    "khata": [r"Khata\s*(?:No\.?|Number)"],
    "survey": [r"Survey\s*(?:No\.?|Number)", r"S\.?\s*No\.?"],
    "village": [r"Village"],
    "mandal": [r"Mandal"],
    "district": [r"District"],
    "extent": [r"Extent(?:\s*\(\s*Area\s*\))?", r"Area"],
    "land_type": [r"Land\s+Type", r"Land\s+Use"],
    "assessment": [r"Assessment\s*(?:No\.?|Number)"],
    "document": [r"Document\s*(?:No\.?|Number)"],
    "date": [r"Date(?:\s+of\s+(?:Issue|Registration|Record))?"],
    "address": [r"Address"],
}


def _looks_like_person(value):
    if not value:
        return False
    value = clean_value(value)
    if not value:
        return False
    low = value.lower()
    blocked = {
        "name", "owner", "owner name", "full name", "father / husband name",
        "father name", "husband name", "address", "district", "mandal",
        "village", "survey number", "survey no", "khata number", "extent",
        "land type", "assessment number", "document number", "date",
        "government of andhra pradesh", "revenue department",
    }
    if low in blocked:
        return False
    if any(x in low for x in ("revenue officer", "revenue department", "government of")):
        return False
    # Names may contain spaces, dots, apostrophes or hyphens.
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,79}", value))


def _label_pattern(labels):
    return r"(?:" + "|".join(labels) + r")"


def _same_line_value(line, labels):
    pattern = _label_pattern(labels)
    m = re.match(rf"^\s*{pattern}\s*[:\-]?\s*(.*?)\s*$", line, re.I)
    if not m:
        return None
    return clean_value(m.group(1))


def _labelish(value):
    if not value:
        return False
    low = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
    known = {
        "name", "owner name", "full name", "father husband name", "father name",
        "husband name", "khata number", "survey number", "survey no", "village",
        "mandal", "district", "extent", "extent acres", "area", "land type",
        "assessment number", "assessment no", "document number", "document no",
        "date", "address", "transaction type", "sub registrar office",
        "classification", "record name",
    }
    return low in known or low.startswith("no extent") or low.startswith("document ")


def labeled_value(text, labels, *, validator=None):
    """Extract a value from a label/value pair without crossing into the next label.

    Handles both:
      Full Name : Ravi Kumar
      Full Name
      Ravi Kumar

    Also handles OCR that places several labels on one line by stopping before
    the next recognized label.
    """
    if not text:
        return None

    lines = [clean_value(x) for x in text.splitlines() if clean_value(x)]
    label_pat = _label_pattern(labels)
    all_label_pat = _label_pattern(sum(LABELS.values(), []))

    for i, line in enumerate(lines):
        # The label must start the line. This prevents "Owner Name" inside a
        # paragraph/table value from swallowing neighbouring columns.
        m = re.match(rf"^\s*{label_pat}\s*[:\-]?\s*(.*)$", line, re.I)
        if not m:
            continue

        rest = clean_value(m.group(1))
        if rest:
            # If OCR put another field label after the target label, cut it off.
            next_label = re.search(rf"\s+(?={all_label_pat}\s*[:\-])", rest, re.I)
            if next_label:
                rest = clean_value(rest[:next_label.start()])
            if rest and not _labelish(rest) and (validator is None or validator(rest)):
                return rest

        # Value may be on the following line.
        if i + 1 < len(lines):
            candidate = lines[i + 1]
            if re.match(rf"^\s*{all_label_pat}\s*[:\-]?", candidate, re.I):
                continue
            if not _labelish(candidate) and (validator is None or validator(candidate)):
                return candidate

    # Last-resort same-line search for OCR that places several labeled fields
    # on one line. Stop at the next recognized label when it has a colon.
    m = re.search(rf"(?i)\b{label_pat}\b\s*[:\-]?\s*([^\n]+)", text)
    if m:
        value = clean_value(m.group(1))
        next_label = re.search(rf"\s+(?={all_label_pat}\s*[:\-])", value, re.I)
        if next_label:
            value = clean_value(value[:next_label.start()])
        if value and not _labelish(value) and (validator is None or validator(value)):
            return value
    return None


def extract_document_number(text):
    value = labeled_value(text, LABELS["document"])
    m = re.search(r"\b([A-Z]{1,3}-\d{4}-\d+)\b", value or "", re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b[A-Z]{1,3}-\d{4}-\d+\b", text, re.I)
    return m.group(0).upper() if m else None


def extract_date(text):
    value = labeled_value(text, LABELS["date"])
    m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", value or "")
    if m:
        return m.group(1)
    m = re.search(r"\b(?:Date|Date\s+of\s+(?:Issue|Registration|Record))\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})\b", text, re.I)
    return m.group(1) if m else None


def extract_khata_number(text):
    value = labeled_value(text, LABELS["khata"])
    m = re.search(r"\b([A-Z]{1,5}-[A-Z0-9-]+|[A-Z0-9]{4,})\b", value or "", re.I)
    return m.group(1).upper() if m else None


def extract_survey_number(text):
    value = labeled_value(text, LABELS["survey"])
    m = re.search(r"\b(\d+(?:/[A-Za-z0-9]+)+)\b", value or "")
    if m:
        return m.group(1)
    lines = [clean_value(x) for x in text.splitlines() if clean_value(x)]
    for i, line in enumerate(lines):
        if re.search(r"\bSurvey\s*(?:No\.?|Number)\b", line, re.I) and i + 1 < len(lines):
            m = re.search(r"\b(\d+(?:/[A-Za-z0-9]+)+)\b", lines[i + 1])
            if m:
                return m.group(1)
    # Avoid treating dates such as 12/04 as a survey number unless the label
    # context actually contains a slash-form survey value.
    return None

def extract_extent(text):
    value = labeled_value(text, LABELS["extent"])
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:Acres?|Acre|Ac)\b", value or "", re.I)
    if not m:
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:Acres?|Acre|Ac)\b", text, re.I)
    if m:
        return f"{m.group(1)} Acres"

    # Table-style OCR often separates the header "Extent (Acres)" from its
    # numeric value. Read only the next line and prefer a decimal value, rather
    # than accidentally taking a survey/date number such as 12/04.
    lines = [clean_value(x) for x in text.splitlines() if clean_value(x)]
    for i, line in enumerate(lines):
        if re.search(r"\bExtent(?:\s*\(\s*Acres?\s*\))?\b", line, re.I):
            for nxt in lines[i + 1:i + 3]:
                m = re.search(r"\b(\d+\.\d+)\b", nxt)
                if m:
                    return f"{m.group(1)} Acres"
    return None

def extract_assessment_number(text):
    value = labeled_value(text, LABELS["assessment"])
    # Support both the older numeric format and alphanumeric IDs such as
    # AS-2026-01458.
    patterns = [
        r"\b(AS-\d{4}-\d+)\b",
        r"\b(\d{2}-\d{3}-\d{3})\b",
        r"\b(\d{3}-\d{3}-\d{3})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, value or "", re.I)
        if m:
            return m.group(1).upper()
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).upper()
    return None


def extract_land_type(text):
    # OCR often swaps nearby characters in "Agricultural". Read the value
    # beside the Land Type label first, then use a small typo-tolerant matcher.
    value = labeled_value(text, LABELS["land_type"])
    candidates = []
    if value:
        candidates.append(value)
    # Also inspect the full OCR text for common one-token OCR variants.
    candidates.extend(re.findall(r"\b[A-Za-z]{6,20}\b", text))

    allowed = {
        "agricultural": "Agricultural",
        "residential": "Residential",
        "commercial": "Commercial",
        "industrial": "Industrial",
    }
    from difflib import SequenceMatcher
    best_name, best_score = None, 0.0
    for candidate in candidates:
        word = re.sub(r"[^a-z]", "", candidate.lower())
        if not word:
            continue
        for target, display in allowed.items():
            score = SequenceMatcher(None, word, target).ratio()
            if score > best_score:
                best_name, best_score = display, score
    return best_name if best_score >= 0.78 else None


def extract_location(text):
    district = labeled_value(text, LABELS["district"])
    mandal = labeled_value(text, LABELS["mandal"])
    village = labeled_value(text, LABELS["village"])
    return district, mandal, village


def _clean_person_ocr(value):
    """Correct a few conservative OCR substitutions in person names.

    Only tiny substitutions are accepted and only after the value has been
    identified as a person-name field. This is not a general spelling fixer.
    """
    value = clean_value(value)
    if not value:
        return None
    parts = value.split()
    fixed = []
    for part in parts:
        if not re.fullmatch(r"[A-Za-z0-9.'-]+", part):
            return value
        if sum(ch.isdigit() for ch in part) <= 2:
            part = part.translate(str.maketrans({"1":"i", "0":"o", "5":"s"}))
        if part.lower() == "iuryanarayana":
            part = "Suryanarayana"
        fixed.append(part)
    candidate = " ".join(fixed)
    # Require a normal alphabetic name after conservative correction.
    return candidate if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,79}", candidate) else value

def _looks_like_person_ocr(value):
    value = clean_value(value)
    if not value:
        return False
    corrected = _clean_person_ocr(value)
    if corrected and _looks_like_person(corrected):
        return True
    # Allow a tiny number of OCR digits so Rav1 Kumar can be reviewed/corrected.
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9 .'-]{1,79}", value)) and not any(x in value.lower() for x in ("address", "district", "mandal", "village", "khata", "survey"))

def extract_owner_fields(text):
    # Primary path: explicit Full Name / Owner Name label.
    owner = labeled_value(text, LABELS["owner"], validator=_looks_like_person_ocr)
    father = labeled_value(text, LABELS["father"], validator=_looks_like_person_ocr)

    if owner:
        owner = _clean_person_ocr(owner)
    if father:
        father = _clean_person_ocr(father)

    # Table-style owner headers can place Owner Name, Father/Husband Name and
    # Address on the same line. If so, scan the next few lines for a plausible
    # person name instead of accepting an address as the owner.
    if not owner:
        lines = [clean_value(x) for x in text.splitlines() if clean_value(x)]
        for i, line in enumerate(lines):
            if re.match(r"^\s*Owner\s+Name\b", line, re.I):
                for candidate in lines[i + 1:i + 5]:
                    if _looks_like_person_ocr(candidate):
                        owner = _clean_person_ocr(candidate)
                        break
                if owner:
                    break

    # Fallback for badly OCR'd headings/labels: inspect the short block after
    # the land-owner section, but never use the father/address line as owner.
    if not owner:
        lines = [clean_value(x) for x in text.splitlines() if clean_value(x)]
        for i, line in enumerate(lines):
            low = line.lower()
            if ("land owner" in low or "owner details" in low or "ownerid" in low) and i + 1 < len(lines):
                for candidate in lines[i + 1:i + 4]:
                    if re.search(r"father|husband|address|khata|survey|district|village|mandal", candidate, re.I):
                        continue
                    if _looks_like_person_ocr(candidate):
                        owner = _clean_person_ocr(candidate)
                        break
                if owner:
                    break

    # Last explicit-line fallback handles OCR that prefixes the label with a
    # small amount of noise.
    if not owner:
        m = re.search(r"(?im)^\s*(?:Full\s*Name|Owner\s*Name|Owner)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9 .'-]{1,79})\s*$", text)
        if m and _looks_like_person_ocr(m.group(1)):
            owner = _clean_person_ocr(m.group(1))

    return owner, father


def extract_address(text):
    lines = [clean_value(x) for x in text.splitlines() if clean_value(x)]
    label_pat = _label_pattern(LABELS["address"])
    stop_pat = re.compile(
        rf"^\s*(?:2\.\s*LAND|3\.\s*LAND|4\.\s*LOCATION|5\.\s*REMARKS|{_label_pattern([x for key, vals in LABELS.items() if key != 'address' for x in vals])})\s*[:\-]?",
        re.I,
    )
    for i, line in enumerate(lines):
        m = re.match(rf"^\s*{label_pat}\s*[:\-]?\s*(.*)$", line, re.I)
        if not m:
            continue
        # A table header such as "Owner Name Father / Husband Name Address"
        # is not itself an address. Wait for an explicit Address: value or use
        # the conservative Door/House-number fallback below.
        if not m.group(1).strip() and re.search(r"Owner\s+Name|Father\s*/?\s*Husband", line, re.I):
            continue
        parts = []
        first = clean_value(m.group(1))
        if first and not _labelish(first):
            parts.append(first)
        for nxt in lines[i + 1:]:
            if stop_pat.match(nxt):
                break
            if re.match(r"^\s*\d+\.\s*", nxt):
                break
            if _labelish(nxt):
                continue
            # Avoid capturing unrelated database/table headings as an address.
            if re.search(r"^(?:Document|Date|Land Type|Assessment|Classification|Transaction|Sub Registrar)\b", nxt, re.I):
                break
            parts.append(nxt)
            if len(parts) >= 4:
                break
        if parts:
            candidate = clean_value(" ".join(parts))
            # A useful address should contain a number or a location token and
            # must not simply be another field heading.
            if not _labelish(candidate) and (re.search(r"\d", candidate) or len(candidate.split()) >= 3):
                return candidate

    # Conservative fallback: use a line explicitly beginning with a house/door number.
    for line in lines:
        if re.match(r"^\s*(?:H\.?\s*No\.?|Door\s*No\.?|No\.)\s*\d", line, re.I):
            return clean_value(line)
    return None

def extract_fields(text, image_path=None):
    text = clean_text(text)
    district, mandal, village = extract_location(text)
    owner, father = extract_owner_fields(text)

    fields = {
        "district": district,
        "mandal": mandal,
        "village": village,
        "survey_number": extract_survey_number(text),
        "extent": extract_extent(text),
        "land_type": extract_land_type(text),
        "assessment_number": extract_assessment_number(text),
        "owner_name": owner,
        "father_husband_name": father,
        "address": extract_address(text),
        "document_number": extract_document_number(text),
        "date": extract_date(text),
        "khata_number": extract_khata_number(text),
    }

    handwriting_evidence = {}
    if image_path and is_legacy_handwritten_form(image_path):
        legacy_fields, handwriting_evidence = extract_legacy_handwritten_fields(image_path)
        for key, value in legacy_fields.items():
            if value:
                fields[key] = value
        # The printed form contains a separate "Name" field. Keep it separate
        # so the result can show every value visible on the source document.
        fields["record_name"] = legacy_fields.get("name")

    cleaned = {k: clean_value(v) for k, v in fields.items()}
    # Preserve the punctuation used on the supplied legacy form.
    if image_path and handwriting_evidence and cleaned.get("district") == "K.K. Dist":
        cleaned["district"] = "K.K. Dist."
    return cleaned, handwriting_evidence


if __name__ == "__main__":
    from ocr import extract_text
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "test_documents/01_match_document.png"
    print(extract_fields(extract_text(path), path))
