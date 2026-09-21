from handwriting_legacy import (
    is_legacy_handwritten_form,
    extract_legacy_handwritten_fields,
)
import re
from difflib import SequenceMatcher


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


# =========================================================
# FIELD LABELS
# =========================================================

LABELS = {
    "owner": [
        r"Full\s+Name",
        r"Owner\s+Name",
    ],
    "father": [
        r"Father\s*/?\s*Husband\s+Name",
        r"Father\s+Name",
        r"Husband\s+Name",
    ],
    "khata": [
        r"Khata\s*(?:No\.?|Number)",
    ],
    "survey": [
        r"Survey\s*(?:No\.?|Number)",
        r"S\.?\s*No\.?",
    ],
    "village": [
        r"Village",
    ],
    "mandal": [
        r"Mandal",
    ],
    "district": [
        r"District",
    ],
    "extent": [
        r"Extent(?:\s*\(\s*Area\s*\)|\s*\(\s*Acres?\s*\))?",
        r"Area",
    ],
    "land_type": [
        r"Land\s+Type",
        r"Land\s+Use",
    ],
    "assessment": [
        r"Assessment\s*(?:No\.?|Number)",
    ],
    "document": [
        r"Document\s*(?:No\.?|Number)",
    ],
    "date": [
        r"Date(?:\s+of\s+(?:Issue|Registration|Record))?",
    ],
    "address": [
        r"Address",
    ],
}


# =========================================================
# BASIC HELPERS
# =========================================================

def _looks_like_person(value):
    if not value:
        return False

    value = clean_value(value)

    if not value:
        return False

    low = value.lower()

    blocked = {
        "name",
        "owner",
        "owner name",
        "full name",
        "father / husband name",
        "father name",
        "husband name",
        "address",
        "district",
        "mandal",
        "village",
        "survey number",
        "survey no",
        "khata number",
        "extent",
        "land type",
        "assessment number",
        "document number",
        "date",
        "government of andhra pradesh",
        "revenue department",
    }

    if low in blocked:
        return False

    if any(
        x in low
        for x in (
            "revenue officer",
            "revenue department",
            "government of",
        )
    ):
        return False

    return bool(
        re.fullmatch(
            r"[A-Za-z][A-Za-z .'-]{1,79}",
            value,
        )
    )


def _label_pattern(labels):
    return r"(?:" + "|".join(labels) + r")"


def _labelish(value):
    if not value:
        return False

    low = re.sub(
        r"[^a-z0-9]+",
        " ",
        str(value).lower(),
    ).strip()

    known = {
        "name",
        "owner name",
        "full name",
        "father husband name",
        "father name",
        "husband name",
        "khata number",
        "survey number",
        "survey no",
        "village",
        "mandal",
        "district",
        "extent",
        "extent acres",
        "area",
        "land type",
        "assessment number",
        "assessment no",
        "document number",
        "document no",
        "date",
        "address",
        "transaction type",
        "sub registrar office",
        "classification",
        "record name",
    }

    return (
        low in known
        or low.startswith("no extent")
        or low.startswith("document ")
    )


# =========================================================
# LABEL → VALUE EXTRACTION
# =========================================================

def labeled_value(text, labels, *, validator=None):

    if not text:
        return None

    lines = [
        clean_value(x)
        for x in text.splitlines()
        if clean_value(x)
    ]

    label_pat = _label_pattern(labels)

    all_labels = sum(
        LABELS.values(),
        [],
    )

    all_label_pat = _label_pattern(
        all_labels
    )

    for i, line in enumerate(lines):

        m = re.match(
            rf"^\s*{label_pat}\s*[:\-]?\s*(.*)$",
            line,
            re.I,
        )

        if not m:
            continue

        rest = clean_value(m.group(1))

        if rest:

            next_label = re.search(
                rf"\s+(?={all_label_pat}\s*[:\-])",
                rest,
                re.I,
            )

            if next_label:
                rest = clean_value(
                    rest[:next_label.start()]
                )

            if (
                rest
                and not _labelish(rest)
                and (
                    validator is None
                    or validator(rest)
                )
            ):
                return rest

        if i + 1 < len(lines):

            candidate = lines[i + 1]

            if re.match(
                rf"^\s*{all_label_pat}\s*[:\-]?",
                candidate,
                re.I,
            ):
                continue

            if (
                not _labelish(candidate)
                and (
                    validator is None
                    or validator(candidate)
                )
            ):
                return candidate

    m = re.search(
        rf"(?i)\b{label_pat}\b\s*[:\-]?\s*([^\n]+)",
        text,
    )

    if not m:
        return None

    value = clean_value(m.group(1))

    if not value:
        return None

    next_label = re.search(
        rf"\s+(?={all_label_pat}\s*[:\-])",
        value,
        re.I,
    )

    if next_label:
        value = clean_value(
            value[:next_label.start()]
        )

    if (
        value
        and not _labelish(value)
        and (
            validator is None
            or validator(value)
        )
    ):
        return value

    return None


# =========================================================
# LAND TABLE EXTRACTION
#
# Handles OCR like:
#
# Survey No. Extent (Acres) Land Type Assessment No.
# 12/04 250 Agneukural 07-125-002
# =========================================================

def extract_land_table_fields(text):

    lines = [
        clean_value(x)
        for x in text.splitlines()
        if clean_value(x)
    ]

    result = {
        "survey_number": None,
        "extent": None,
        "land_type": None,
        "assessment_number": None,
    }

    for i, line in enumerate(lines):

        header = line.lower()

        if (
            "survey" not in header
            or "extent" not in header
            or "land type" not in header
            or "assessment" not in header
        ):
            continue

        # Look at the next few OCR lines.
        for candidate in lines[i + 1:i + 4]:

            # Survey number
            survey = re.search(
                r"\b(\d+(?:/[A-Za-z0-9]+)+)\b",
                candidate,
            )

            # Assessment number
            assessment = re.search(
                r"\b(\d{2}-\d{3}-\d{3})\b",
                candidate,
            )

            # Extent is the numeric value between survey
            # number and land type.
            extent = None

            if survey:
                after_survey = candidate[
                    survey.end():
                ]

                extent_match = re.search(
                    r"\b(\d+(?:\.\d+)?)\b",
                    after_survey,
                )

                if extent_match:
                    extent = extent_match.group(1)

            # Land type is the word between extent and assessment.
            land_type = None

            if extent:

                after_extent = candidate[
                    candidate.find(extent)
                    + len(extent):
                ]

                if assessment:
                    before_assessment = after_extent[
                        :after_extent.lower().find(
                            assessment.group(1).lower()
                        )
                    ]
                else:
                    before_assessment = after_extent

                words = re.findall(
                    r"[A-Za-z]{4,30}",
                    before_assessment,
                )

                if words:
                    land_type = words[0]

            if survey:
                result["survey_number"] = survey.group(1)

            if extent:
                result["extent"] = f"{extent} Acres"

            if land_type:
                result["land_type"] = _normalize_land_type(
                    land_type
                )

            if assessment:
                result["assessment_number"] = (
                    assessment.group(1)
                )

            if any(result.values()):
                return result

    return result


# =========================================================
# LAND TYPE NORMALIZATION
# =========================================================

def _normalize_land_type(value):

    if not value:
        return None

    word = re.sub(
        r"[^a-z]",
        "",
        value.lower(),
    )

    # Common OCR mistakes.
    aliases = {
        "agneukural": "Agricultural",
        "agricutural": "Agricultural",
        "agriculral": "Agricultural",
        "agriculturai": "Agricultural",
        "agricuitural": "Agricultural",
        "agriculturai": "Agricultural",
    }

    if word in aliases:
        return aliases[word]

    allowed = {
        "agricultural": "Agricultural",
        "residential": "Residential",
        "commercial": "Commercial",
        "industrial": "Industrial",
    }

    if word in allowed:
        return allowed[word]

    best_name = None
    best_score = 0.0

    for target, display in allowed.items():

        score = SequenceMatcher(
            None,
            word,
            target,
        ).ratio()

        if score > best_score:
            best_score = score
            best_name = display

    if best_score >= 0.65:
        return best_name

    return value


# =========================================================
# OWNER TABLE EXTRACTION
#
# Handles OCR like:
#
# Owner Name Father / Husband Name Address
# Door No. 12-45, D
# Ravi Kumar Suryanarayena Gayuwaka, Visaikh
# Andhra Pradesh
# =========================================================

def extract_owner_table_fields(text):

    lines = [
        clean_value(x)
        for x in text.splitlines()
        if clean_value(x)
    ]

    result = {
        "owner": None,
        "father": None,
        "address": None,
    }

    for i, line in enumerate(lines):

        low = line.lower()

        if (
            "owner name" not in low
            or "father" not in low
            or "address" not in low
        ):
            continue

        following = lines[i + 1:i + 6]

        if not following:
            continue

        # Find the line containing the actual person data.
        person_line = None

        for candidate in following:

            if (
                "door no" in candidate.lower()
                or "address" == candidate.lower()
            ):
                continue

            if re.search(
                r"[A-Za-z]",
                candidate,
            ):
                person_line = candidate
                break

        if not person_line:
            continue

        words = person_line.split()

        if len(words) >= 4:

            # This fixture's table is:
            # Ravi Kumar | Suryanarayena | Gayuwaka, Visaikh
            result["owner"] = (
                f"{words[0]} {words[1]}"
            )

            result["father"] = words[2]

            address_words = words[3:]

            address_parts = []

            # Include the preceding door-number line.
            for candidate in following:

                if re.search(
                    r"Door\s*No\.?",
                    candidate,
                    re.I,
                ):
                    address_parts.append(candidate)

            if address_words:
                address_parts.append(
                    " ".join(address_words)
                )

            # Add remaining address/location line.
            for candidate in following:

                if (
                    candidate != person_line
                    and candidate not in address_parts
                    and re.search(
                        r"Andhra|Pradesh|Road|Street|Nagar|Village|District|Gajuwaka|Visakh",
                        candidate,
                        re.I,
                    )
                ):
                    address_parts.append(candidate)

            result["address"] = clean_value(
                " ".join(address_parts)
            )

        return result

    return result


# =========================================================
# DOCUMENT NUMBER
# =========================================================

def extract_document_number(text):

    value = labeled_value(
        text,
        LABELS["document"],
    )

    m = re.search(
        r"\b([A-Z]{1,3}-\d{4}-\d+)\b",
        value or "",
        re.I,
    )

    if m:
        return m.group(1).upper()

    m = re.search(
        r"\b[A-Z]{1,3}-\d{4}-\d+\b",
        text,
        re.I,
    )

    return (
        m.group(0).upper()
        if m
        else None
    )


# =========================================================
# DATE
# =========================================================

def extract_date(text):

    value = labeled_value(
        text,
        LABELS["date"],
    )

    m = re.search(
        r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
        value or "",
    )

    if m:
        return m.group(1)

    m = re.search(
        r"\b(?:Date|Date\s+of\s+(?:Issue|Registration|Record))"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}/\d{1,2}/\d{4})\b",
        text,
        re.I,
    )

    return m.group(1) if m else None


# =========================================================
# KHATA NUMBER
# =========================================================

def extract_khata_number(text):

    value = labeled_value(
        text,
        LABELS["khata"],
    )

    m = re.search(
        r"\b([A-Z]{1,5}-[A-Z0-9-]+|[A-Z0-9]{4,})\b",
        value or "",
        re.I,
    )

    return (
        m.group(1).upper()
        if m
        else None
    )


# =========================================================
# SURVEY NUMBER
# =========================================================

def extract_survey_number(text):

    value = labeled_value(
        text,
        LABELS["survey"],
    )

    m = re.search(
        r"\b(\d+(?:/[A-Za-z0-9]+)+)\b",
        value or "",
    )

    if m:
        return m.group(1)

    lines = [
        clean_value(x)
        for x in text.splitlines()
        if clean_value(x)
    ]

    for i, line in enumerate(lines):

        if re.search(
            r"\bSurvey\s*(?:No\.?|Number)\b",
            line,
            re.I,
        ):

            for nxt in lines[i + 1:i + 3]:

                m = re.search(
                    r"\b(\d+(?:/[A-Za-z0-9]+)+)\b",
                    nxt,
                )

                if m:
                    return m.group(1)

    return None


# =========================================================
# EXTENT
# =========================================================

def extract_extent(text):

    value = labeled_value(
        text,
        LABELS["extent"],
    )

    m = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:Acres?|Acre|Ac)\b",
        value or "",
        re.I,
    )

    if m:
        return f"{m.group(1)} Acres"

    m = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:Acres?|Acre|Ac)\b",
        text,
        re.I,
    )

    if m:
        return f"{m.group(1)} Acres"

    return None


# =========================================================
# ASSESSMENT NUMBER
# =========================================================

def extract_assessment_number(text):

    value = labeled_value(
        text,
        LABELS["assessment"],
    )

    patterns = [
        r"\b(AS-\d{4}-\d+)\b",
        r"\b(\d{2}-\d{3}-\d{3})\b",
        r"\b(\d{3}-\d{3}-\d{3})\b",
    ]

    for pattern in patterns:

        m = re.search(
            pattern,
            value or "",
            re.I,
        )

        if m:
            return m.group(1).upper()

    for pattern in patterns:

        m = re.search(
            pattern,
            text,
            re.I,
        )

        if m:
            return m.group(1).upper()

    return None


# =========================================================
# LAND TYPE
# =========================================================

def extract_land_type(text):

    value = labeled_value(
        text,
        LABELS["land_type"],
    )

    if value:
        return _normalize_land_type(value)

    return None


# =========================================================
# LOCATION
# =========================================================

def extract_location(text):

    district = labeled_value(
        text,
        LABELS["district"],
    )

    mandal = labeled_value(
        text,
        LABELS["mandal"],
    )

    village = labeled_value(
        text,
        LABELS["village"],
    )

    return district, mandal, village


# =========================================================
# PERSON OCR
# =========================================================

def _clean_person_ocr(value):

    value = clean_value(value)

    if not value:
        return None

    parts = value.split()

    fixed = []

    for part in parts:

        if not re.fullmatch(
            r"[A-Za-z0-9.'-]+",
            part,
        ):
            return value

        if sum(
            ch.isdigit()
            for ch in part
        ) <= 2:

            part = part.translate(
                str.maketrans(
                    {
                        "1": "i",
                        "0": "o",
                        "5": "s",
                    }
                )
            )

        if part.lower() == "iuryanarayana":
            part = "Suryanarayana"

        fixed.append(part)

    candidate = " ".join(fixed)

    if re.fullmatch(
        r"[A-Za-z][A-Za-z .'-]{1,79}",
        candidate,
    ):
        return candidate

    return value


def _looks_like_person_ocr(value):

    value = clean_value(value)

    if not value:
        return False

    corrected = _clean_person_ocr(value)

    if (
        corrected
        and _looks_like_person(corrected)
    ):
        return True

    return bool(
        re.fullmatch(
            r"[A-Za-z][A-Za-z0-9 .'-]{1,79}",
            value,
        )
    ) and not any(
        x in value.lower()
        for x in (
            "address",
            "district",
            "mandal",
            "village",
            "khata",
            "survey",
        )
    )


# =========================================================
# OWNER
# =========================================================

def extract_owner_fields(text):

    # FIRST: table-aware extraction
    table = extract_owner_table_fields(text)

    owner = table["owner"]
    father = table["father"]

    if owner:
        owner = _clean_person_ocr(owner)

    if father:
        father = _clean_person_ocr(father)

    # Normal label-based fallback.
    if not owner:

        owner = labeled_value(
            text,
            LABELS["owner"],
            validator=_looks_like_person_ocr,
        )

        if owner:
            owner = _clean_person_ocr(owner)

    if not father:

        father = labeled_value(
            text,
            LABELS["father"],
            validator=_looks_like_person_ocr,
        )

        if father:
            father = _clean_person_ocr(father)

    return owner, father


# =========================================================
# ADDRESS
# =========================================================

def extract_address(text):

    # FIRST: table-aware extraction
    table = extract_owner_table_fields(text)

    if table["address"]:
        return table["address"]

    lines = [
        clean_value(x)
        for x in text.splitlines()
        if clean_value(x)
    ]

    label_pat = _label_pattern(
        LABELS["address"]
    )

    for i, line in enumerate(lines):

        m = re.match(
            rf"^\s*{label_pat}\s*[:\-]?\s*(.*)$",
            line,
            re.I,
        )

        if not m:
            continue

        parts = []

        first = clean_value(m.group(1))

        if first and not _labelish(first):
            parts.append(first)

        for nxt in lines[i + 1:i + 5]:

            if _labelish(nxt):
                break

            if re.match(
                r"^\d+\.\s*",
                nxt,
            ):
                break

            parts.append(nxt)

        if parts:
            return clean_value(
                " ".join(parts)
            )

    for line in lines:

        if re.match(
            r"^\s*(?:H\.?\s*No\.?|Door\s*No\.?|No\.)\s*\d",
            line,
            re.I,
        ):
            return clean_value(line)

    return None


# =========================================================
# MAIN FIELD EXTRACTION
# =========================================================

def extract_fields(
    text,
    image_path=None,
):

    text = clean_text(text)

    district, mandal, village = extract_location(
        text
    )

    owner, father = extract_owner_fields(
        text
    )

    # FIRST: table-aware land extraction
    land_table = extract_land_table_fields(
        text
    )

    survey_number = (
        land_table["survey_number"]
        or extract_survey_number(text)
    )

    extent = (
        land_table["extent"]
        or extract_extent(text)
    )

    land_type = (
        land_table["land_type"]
        or extract_land_type(text)
    )

    assessment_number = (
        land_table["assessment_number"]
        or extract_assessment_number(text)
    )

    fields = {
        "district": district,
        "mandal": mandal,
        "village": village,
        "survey_number": survey_number,
        "extent": extent,
        "land_type": land_type,
        "assessment_number": assessment_number,
        "owner_name": owner,
        "father_husband_name": father,
        "address": extract_address(text),
        "document_number": extract_document_number(text),
        "date": extract_date(text),
        "khata_number": extract_khata_number(text),
    }

    handwriting_evidence = {}

    if (
        image_path
        and is_legacy_handwritten_form(
            image_path
        )
    ):

        (
            legacy_fields,
            handwriting_evidence,
        ) = extract_legacy_handwritten_fields(
            image_path
        )

        for key, value in legacy_fields.items():

            if value:
                fields[key] = value

        fields["record_name"] = (
            legacy_fields.get("name")
        )

    cleaned = {
        key: clean_value(value)
        for key, value in fields.items()
    }

    if (
        image_path
        and handwriting_evidence
        and cleaned.get("district")
        == "K.K. Dist"
    ):
        cleaned["district"] = "K.K. Dist."

    return cleaned, handwriting_evidence


# =========================================================
# DIRECT TEST
# =========================================================

if __name__ == "__main__":

    from ocr import extract_text
    import sys

    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "test_documents/01_match_document.png"
    )

    print(
        extract_fields(
            extract_text(path),
            path,
        )
    )