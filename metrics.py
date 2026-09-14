"""Evaluation metrics for Dhara-Netra AI.

These are evaluation metrics, not legal authenticity measures. A production evaluation
should use manually verified ground-truth annotations.
"""
import math

def _levenshtein(a, b):
    a, b = str(a or ""), str(b or "")
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j-1] + (ca != cb)))
        prev = cur
    return prev[-1]

def cer(reference, prediction):
    ref = str(reference or "")
    if not ref:
        return 0.0 if not prediction else 1.0
    return _levenshtein(ref, str(prediction or "")) / len(ref)

def _sequence_levenshtein(ref, pred):
    ref, pred = list(ref), list(pred)
    prev = list(range(len(pred) + 1))
    for i, token in enumerate(ref, 1):
        cur = [i]
        for j, other in enumerate(pred, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j-1] + (token.casefold() != other.casefold())))
        prev = cur
    return prev[-1]

def wer(reference, prediction):
    ref = str(reference or "").split()
    pred = str(prediction or "").split()
    if not ref:
        return 0.0 if not pred else 1.0
    return _sequence_levenshtein(ref, pred) / len(ref)

def exact_match(reference, prediction):
    return 1.0 if str(reference or "").strip().casefold() == str(prediction or "").strip().casefold() else 0.0

def precision_recall_f1(tp, fp, fn):
    tp, fp, fn = float(tp), float(fp), float(fn)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}

def completeness(extracted, required):
    required = list(required or [])
    if not required:
        return 1.0
    return sum(bool(extracted.get(k)) for k in required) / len(required)

def mismatch_rate(comparisons):
    vals = [v for v in (comparisons or {}).values() if v.get("status") in {"MATCH", "MISMATCH"}]
    if not vals:
        return 0.0
    return sum(v["status"] == "MISMATCH" for v in vals) / len(vals)

def expected_calibration_error(confidences, correctness, bins=10):
    """ECE for confidence values in [0,1] and binary correctness values."""
    if not confidences:
        return 0.0
    total = len(confidences)
    ece = 0.0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        members = [j for j,c in enumerate(confidences) if (lo <= c < hi) or (i == bins-1 and c == hi)]
        if not members:
            continue
        avg_conf = sum(confidences[j] for j in members) / len(members)
        avg_acc = sum(correctness[j] for j in members) / len(members)
        ece += len(members) / total * abs(avg_conf - avg_acc)
    return ece
