"""Bounded OCR runtime for Dhara-Netra AI.

The hosted prototype must fail safely on small/free instances. OCR is deliberately
bounded by image size, page count and subprocess timeouts. PDF pages are rendered
one at a time so a large PDF cannot be loaded into memory all at once.
"""
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import os
import shutil
import tempfile
import pytesseract

MAX_OCR_DIMENSION = int(os.environ.get("MAX_OCR_DIMENSION", "1200"))
OCR_TIMEOUT_SECONDS = int(os.environ.get("OCR_TIMEOUT_SECONDS", "8"))
PDF_MAX_PAGES = int(os.environ.get("PDF_MAX_PAGES", "3"))
PDF_RENDER_SCALE = float(os.environ.get("PDF_RENDER_SCALE", "1.25"))


def _configure_tesseract():
    candidates = [
        os.environ.get("TESSERACT_CMD", "").strip(),
        shutil.which("tesseract") or "",
        r"C:\\Program Files\\Tesseract-OCR\tesseract.exe",
        r"C:\\Program Files (x86)\\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate
    return None


TESSERACT_CMD = _configure_tesseract()


def tesseract_status():
    try:
        version = str(pytesseract.get_tesseract_version()).splitlines()[0].strip()
        return {
            "available": True,
            "version": version,
            "command": pytesseract.pytesseract.tesseract_cmd,
            "ocr_timeout_seconds": OCR_TIMEOUT_SECONDS,
            "max_ocr_dimension": MAX_OCR_DIMENSION,
            "pdf_max_pages": PDF_MAX_PAGES,
        }
    except Exception as exc:
        return {
            "available": False,
            "version": None,
            "command": pytesseract.pytesseract.tesseract_cmd,
            "error": str(exc),
            "ocr_timeout_seconds": OCR_TIMEOUT_SECONDS,
            "max_ocr_dimension": MAX_OCR_DIMENSION,
            "pdf_max_pages": PDF_MAX_PAGES,
        }


def _bound_image(image):
    image = image.convert("RGB")
    if max(image.size) > MAX_OCR_DIMENSION:
        image.thumbnail((MAX_OCR_DIMENSION, MAX_OCR_DIMENSION), Image.Resampling.LANCZOS)
    return image


def _load_image(image_path):
    try:
        return _bound_image(Image.open(image_path))
    except Exception as exc:
        raise RuntimeError(f"Unable to open uploaded image: {exc}") from exc


def _run_ocr(image, timeout=None):
    timeout = timeout or OCR_TIMEOUT_SECONDS
    try:
        return pytesseract.image_to_string(
            image,
            config="--psm 3",
            timeout=timeout,
        ).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR is not available in the server runtime."
        ) from exc
    except RuntimeError as exc:
        if "timeout" in str(exc).lower():
            raise TimeoutError(f"OCR timed out after {timeout} seconds") from exc
        raise RuntimeError(f"Tesseract OCR failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Tesseract OCR failed: {exc}") from exc


def _extract_pdf_text(pdf_path):
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PDF support is unavailable in this deployment.") from exc

    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            raise RuntimeError("The uploaded PDF contains no pages.")
        total_pages = doc.page_count
        page_count = min(total_pages, PDF_MAX_PAGES)
        chunks = []
        for index in range(page_count):
            page = doc.load_page(index)
            pix = page.get_pixmap(matrix=fitz.Matrix(PDF_RENDER_SCALE, PDF_RENDER_SCALE), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            image = _bound_image(image)
            try:
                text = _run_ocr(image)
            except TimeoutError:
                # A PDF page that is too complex gets one smaller, faster pass.
                image.thumbnail((850, 850), Image.Resampling.LANCZOS)
                try:
                    text = _run_ocr(image, timeout=4)
                except Exception as exc:
                    raise RuntimeError(
                        f"OCR could not process PDF page {index + 1} within the hosted resource limit."
                    ) from exc
            if text:
                chunks.append(f"[PAGE {index + 1}]\n{text}")
        doc.close()
        if not chunks:
            raise RuntimeError("OCR found no readable text in the uploaded PDF.")
        if total_pages > PDF_MAX_PAGES:
            chunks.append(f"[SYSTEM NOTE] Only the first {PDF_MAX_PAGES} pages were processed by the prototype.")
        return "\n\n".join(chunks)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Unable to process PDF: {exc}") from exc


def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return _extract_pdf_text(file_path)

    image = _load_image(file_path)
    try:
        text = _run_ocr(image)
    except TimeoutError:
        fallback = image.copy()
        fallback.thumbnail((850, 850), Image.Resampling.LANCZOS)
        try:
            text = _run_ocr(fallback, timeout=4)
        except Exception as exc:
            raise RuntimeError(
                "OCR could not finish within the hosted resource limit. "
                "Try a clearer JPG/PNG scan with less background detail."
            ) from exc

    if not text:
        raise RuntimeError(
            "OCR returned no readable text from the uploaded document. "
            "Try a clearer scan."
        )
    return text


def extract_ocr_token_confidence(file_path):
    """Supplementary confidence data. It is intentionally disabled by default."""
    if os.environ.get("SKIP_OCR_TOKEN_CONFIDENCE", "1") == "1":
        return []
    if os.path.splitext(file_path)[1].lower() == ".pdf":
        return []
    image = _load_image(file_path)
    try:
        data = pytesseract.image_to_data(
            image,
            config="--psm 3",
            output_type=pytesseract.Output.DICT,
            timeout=OCR_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        print(f"[OCR] optional token-confidence pass skipped: {exc}")
        return []
    rows = []
    for i, raw in enumerate(data.get("text", [])):
        word = (raw or "").strip()
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        if word and conf >= 0:
            rows.append({"text": word, "confidence": conf})
    return rows
