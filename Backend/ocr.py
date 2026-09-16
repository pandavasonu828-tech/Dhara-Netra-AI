"""OCR runtime for Dhara-Netra AI.

Render/free containers have limited CPU and memory.  The production-shaped
prototype therefore keeps OCR bounded: uploaded images are resized before
processing, Tesseract calls have hard timeouts, and token-confidence extraction
fails soft instead of killing the web worker.
"""
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract
import os
import shutil

# Keep the OCR request bounded on small Render instances.
MAX_OCR_DIMENSION = int(os.environ.get("MAX_OCR_DIMENSION", "1400"))
OCR_TIMEOUT_SECONDS = int(os.environ.get("OCR_TIMEOUT_SECONDS", "15"))


def _configure_tesseract():
    candidates = [
        os.environ.get("TESSERACT_CMD", "").strip(),
        shutil.which("tesseract") or "",
        r"C:\\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\\Program Files (x86)\Tesseract-OCR\tesseract.exe",
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
        return {
            "available": True,
            "version": version,
            "command": pytesseract.pytesseract.tesseract_cmd,
            "ocr_timeout_seconds": OCR_TIMEOUT_SECONDS,
            "max_ocr_dimension": MAX_OCR_DIMENSION,
        }
    except Exception as exc:
        return {
            "available": False,
            "version": None,
            "command": pytesseract.pytesseract.tesseract_cmd,
            "error": str(exc),
            "ocr_timeout_seconds": OCR_TIMEOUT_SECONDS,
            "max_ocr_dimension": MAX_OCR_DIMENSION,
        }


def _load_for_ocr(image_path):
    """Load an image and bound its size so OCR cannot consume excessive CPU/RAM."""
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception as exc:
        raise RuntimeError(f"Unable to open uploaded image: {exc}") from exc

    if max(image.size) > MAX_OCR_DIMENSION:
        image.thumbnail((MAX_OCR_DIMENSION, MAX_OCR_DIMENSION), Image.Resampling.LANCZOS)
    return image


def _run_ocr(image, config="--psm 6"):
    try:
        return pytesseract.image_to_string(
            image,
            config=config,
            timeout=OCR_TIMEOUT_SECONDS,
        ).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR is not available in the server runtime. "
            "The Docker image must install tesseract-ocr."
        ) from exc
    except RuntimeError as exc:
        # pytesseract uses RuntimeError for its subprocess timeout.
        if "timeout" in str(exc).lower():
            raise RuntimeError(
                f"OCR timed out after {OCR_TIMEOUT_SECONDS} seconds. "
                "The image was too complex for the available server resources."
            ) from exc
        raise RuntimeError(f"Tesseract OCR failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Tesseract OCR failed: {exc}") from exc


def preprocess_image(image_path):
    image = _load_for_ocr(image_path)
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
    """Run bounded OCR suitable for a small Render instance.

    The first pass uses a downscaled original image to preserve identifiers
    while keeping CPU/RAM bounded. If that pass times out, a smaller sparse
    text pass is attempted instead of letting the web worker hang.
    """
    image = _load_for_ocr(image_path)
    try:
        text = _run_ocr(image, config="--psm 6")
    except RuntimeError as exc:
        if "timed out" not in str(exc).lower():
            raise
        # Last-resort pass for unusually complex scans (maps/stamps/backgrounds).
        fallback = image.copy()
        fallback.thumbnail((900, 900), Image.Resampling.LANCZOS)
        try:
            text = pytesseract.image_to_string(
                fallback, config="--psm 11", timeout=10
            ).strip()
        except Exception as fallback_exc:
            raise RuntimeError(
                "OCR could not finish within the hosted resource limit. "
                "Please upload a clearer JPG/PNG scan with less background detail."
            ) from fallback_exc

    if not text.strip():
        raise RuntimeError(
            "OCR returned no readable text from the uploaded image. "
            "Try a clearer JPG/PNG scan."
        )
    return text

def extract_ocr_token_confidence(image_path):
    """Return token confidence data using one additional bounded OCR pass.

    If this optional diagnostic pass times out, return an empty list so the
    document can still be processed instead of terminating the request.
    """
    image = _load_for_ocr(image_path)
    try:
        data = pytesseract.image_to_data(
            image,
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
            timeout=OCR_TIMEOUT_SECONDS,
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError("Tesseract OCR is not available in the server runtime.") from exc
    except Exception as exc:
        # Confidence is supplementary. Never fail an otherwise valid OCR result
        # because this optional pass is slow or unavailable.
        print(f"[OCR] token-confidence pass skipped: {exc}")
        return []

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
