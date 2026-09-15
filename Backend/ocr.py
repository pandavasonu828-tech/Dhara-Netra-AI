"""OCR runtime for Dhara-Netra AI.

The same code runs on Windows and in the Linux Docker/Render container.
Tesseract is discovered from the environment/PATH instead of assuming a
Windows installation path.
"""
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract
import os
import shutil


def _configure_tesseract():
    candidates = [
        os.environ.get("TESSERACT_CMD", "").strip(),
        shutil.which("tesseract") or "",
        r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
        r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate
    return None


TESSERACT_CMD = _configure_tesseract()


def tesseract_status():
    """Return a safe runtime diagnostic used by the health endpoint."""
    try:
        version = str(pytesseract.get_tesseract_version()).splitlines()[0].strip()
        return {"available": True, "version": version, "command": pytesseract.pytesseract.tesseract_cmd}
    except Exception as exc:
        return {"available": False, "version": None, "command": pytesseract.pytesseract.tesseract_cmd, "error": str(exc)}


def _run_ocr(image, config="--psm 6"):
    try:
        return pytesseract.image_to_string(image, config=config).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR is not available in the server runtime. "
            "The Docker image must install tesseract-ocr."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Tesseract OCR failed: {exc}") from exc


def preprocess_image(image_path):
    image = Image.open(image_path).convert("RGB")
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    gray = ImageEnhance.Contrast(gray).enhance(1.25)
    return gray


def _ocr_score(text):
    if not text:
        return 0
    labels = (
        "owner", "survey", "village", "district", "mandal", "extent",
        "land", "assessment", "document", "address", "father", "government"
    )
    low = text.lower()
    return len(text) + sum(80 for label in labels if label in low)


def extract_text(image_path):
    """Run OCR with a conservative original-image pass plus a fallback pass.

    The original image is preferred because aggressive preprocessing can change
    survey identifiers such as 145/2A into 145/24.
    """
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception as exc:
        raise RuntimeError(f"Unable to open uploaded image: {exc}") from exc

    original = _run_ocr(image, config="--psm 6")
    candidates = [original]

    # Only use enhancement as a fallback/candidate. This helps faded scans while
    # preserving the original OCR result when it contains useful field labels.
    try:
        enhanced = preprocess_image(image_path)
        candidates.append(_run_ocr(enhanced, config="--psm 6"))
    except Exception:
        # Original OCR is still useful; do not hide its result because an optional
        # enhancement pass failed.
        pass

    best = max(candidates, key=_ocr_score, default="")
    if not best.strip():
        raise RuntimeError("OCR returned no readable text from the uploaded image. Try a clearer JPG/PNG scan.")
    return best


def extract_ocr_token_confidence(image_path):
    image = Image.open(image_path).convert("RGB")
    try:
        data = pytesseract.image_to_data(image, config="--psm 6", output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError("Tesseract OCR is not available in the server runtime.") from exc
    rows = []
    for i, raw in enumerate(data["text"]):
        word = (raw or "").strip()
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        if word and conf >= 0:
            rows.append({"text": word, "confidence": conf})
    return rows
