import re

def clamp(value, low=0, high=99):
    return max(low, min(high, round(value)))

def _norm(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())

def calculate_confidence(fields, validation, comparisons=None, ocr_tokens=None):
    """Prototype field-level verification confidence.

    This is NOT a calibrated probability. It combines OCR token evidence,
    deterministic validation and (when supplied) citizen/document comparison.
    Exact verified matches receive a high score because independent evidence
    agrees; missing fields remain 0 and are routed to human review.
    """
    comparisons = comparisons or {}
    tokens = ocr_tokens or []
    token_text = {}
    for t in tokens:
        key = _norm(t.get("text", ""))
        if key:
            token_text.setdefault(key, []).append(float(t.get("confidence", 0)))

    confidence = {}
    for field, value in fields.items():
        if not value:
            confidence[field] = {"score": 0, "status": "NEEDS_REVIEW", "reason": "Field was not extracted"}
            continue

        words = [_norm(w) for w in re.split(r"\s+", str(value)) if _norm(w)]
        matched_scores = []
        for word in words:
            if word in token_text:
                matched_scores.append(max(token_text[word]))
        ocr_score = sum(matched_scores) / len(matched_scores) if matched_scores else 70.0
        validation_score = 95.0 if validation.get(field, {}).get("status") == "VALID" else 60.0
        # Explainable prototype components: OCR evidence + rule validation + cross-source agreement.
        base = 0.65 * ocr_score + 0.35 * validation_score

        comparison = comparisons.get(field)
        if comparison:
            status = comparison.get("status")
            if status == "MATCH":
                # Agreement between citizen reference and extracted value is
                # strong verification evidence. Do not let a single noisy OCR
                # token produce an implausibly low score for an exact match.
                base = max(base + 5.0, 90.0)
            elif status == "MISMATCH":
                base -= 25.0
            elif status == "NEEDS_REVIEW":
                base -= 15.0

        score = clamp(base)
        comparison_status = comparison.get("status") if comparison else "NOT_COMPARED"
        confidence[field] = {
            "score": score,
            "components": {
                "ocr_evidence": round(ocr_score),
                "rule_validation": round(validation_score),
                "cross_source": comparison_status,
            },
            "status": "VERIFIED" if score >= 80 else "NEEDS_REVIEW",
            "reason": "OCR evidence + rule validation + comparison" if comparison else "OCR evidence + rule validation",
        }
    return confidence
