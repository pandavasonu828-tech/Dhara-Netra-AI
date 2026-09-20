"""Bounded OCR runtime for Dhara-Netra AI.

Optimized for small/free hosted instances.

The OCR pipeline:
- limits image dimensions
- preprocesses images for faster OCR
- uses a lightweight Tesseract page mode
- performs only one OCR pass
- processes PDF pages one at a time
- gives useful error messages
"""

from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import os
import shutil
import pytesseract


# ---------------------------------------------------------
# OCR CONFIGURATION
# ---------------------------------------------------------

MAX_OCR_DIMENSION = int(
    os.environ.get("MAX_OCR_DIMENSION", "1000")
)

OCR_TIMEOUT_SECONDS = int(
    os.environ.get("OCR_TIMEOUT_SECONDS", "20")
)

PDF_MAX_PAGES = int(
    os.environ.get("PDF_MAX_PAGES", "3")
)

PDF_RENDER_SCALE = float(
    os.environ.get("PDF_RENDER_SCALE", "1.0")
)

# Keep OCR slightly below the hosted image limit.
# This reduces CPU usage while preserving enough detail
# for normal printed documents.
OCR_TARGET_DIMENSION = min(
    MAX_OCR_DIMENSION,
    900
)


# ---------------------------------------------------------
# TESSERACT CONFIGURATION
# ---------------------------------------------------------

def _configure_tesseract():
    candidates = [
        os.environ.get("TESSERACT_CMD", "").strip(),
        shutil.which("tesseract") or "",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate

    return None


TESSERACT_CMD = _configure_tesseract()


# ---------------------------------------------------------
# TESSERACT STATUS
# ---------------------------------------------------------

def tesseract_status():
    try:
        version = str(
            pytesseract.get_tesseract_version()
        ).splitlines()[0].strip()

        return {
            "available": True,
            "version": version,
            "command": pytesseract.pytesseract.tesseract_cmd,
            "ocr_timeout_seconds": OCR_TIMEOUT_SECONDS,
            "max_ocr_dimension": MAX_OCR_DIMENSION,
            "ocr_target_dimension": OCR_TARGET_DIMENSION,
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
            "ocr_target_dimension": OCR_TARGET_DIMENSION,
            "pdf_max_pages": PDF_MAX_PAGES,
        }


# ---------------------------------------------------------
# IMAGE SIZE LIMIT
# ---------------------------------------------------------

def _bound_image(image, target=None):
    image = image.convert("RGB")

    target = target or OCR_TARGET_DIMENSION

    if max(image.size) > target:
        image.thumbnail(
            (target, target),
            Image.Resampling.LANCZOS
        )

    return image


# ---------------------------------------------------------
# OCR PREPROCESSING
# ---------------------------------------------------------

def _preprocess_image(image):
    """Prepare image for lightweight Tesseract OCR."""

    image = _bound_image(
        image,
        OCR_TARGET_DIMENSION
    )

    # Convert to grayscale.
    gray = ImageOps.grayscale(image)

    # Improve contrast.
    gray = ImageOps.autocontrast(
        gray,
        cutoff=1
    )

    # Slight sharpening.
    gray = ImageEnhance.Sharpness(
        gray
    ).enhance(1.3)

    # Small noise reduction.
    gray = gray.filter(
        ImageFilter.MedianFilter(size=3)
    )

    return gray


# ---------------------------------------------------------
# LOAD IMAGE
# ---------------------------------------------------------

def _load_image(image_path):
    try:
        with Image.open(image_path) as source:
            image = source.copy()

        return _bound_image(
            image,
            OCR_TARGET_DIMENSION
        )

    except Exception as exc:
        raise RuntimeError(
            f"Unable to open uploaded image: {exc}"
        ) from exc


# ---------------------------------------------------------
# RUN TESSERACT OCR
# ---------------------------------------------------------

def _run_ocr(image, timeout=None):
    timeout = (
        timeout
        if timeout is not None
        else OCR_TIMEOUT_SECONDS
    )

    try:
        # PSM 6 is lighter than PSM 3 for ordinary
        # scanned forms and document pages.
        return pytesseract.image_to_string(
            image,
            config="--oem 3 --psm 6",
            timeout=timeout,
        ).strip()

    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR is not available "
            "in the server runtime."
        ) from exc

    except RuntimeError as exc:
        message = str(exc)

        if "timeout" in message.lower():
            raise TimeoutError(
                f"OCR timed out after {timeout} seconds"
            ) from exc

        raise RuntimeError(
            f"Tesseract OCR failed: {message}"
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            f"Tesseract OCR failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


# ---------------------------------------------------------
# OCR ONE IMAGE
# ---------------------------------------------------------

def _extract_image_text(image, source_name="image"):
    """Run exactly one optimized OCR pass."""

    processed = _preprocess_image(image)

    try:
        text = _run_ocr(
            processed,
            timeout=OCR_TIMEOUT_SECONDS
        )

    except TimeoutError as exc:
        raise RuntimeError(
            f"OCR timed out after "
            f"{OCR_TIMEOUT_SECONDS} seconds for "
            f"{source_name}. "
            f"The hosted OCR engine could not process "
            f"this document within the available "
            f"CPU limit."
        ) from exc

    if not text:
        raise RuntimeError(
            f"OCR completed but found no readable "
            f"text in {source_name}."
        )

    return text


# ---------------------------------------------------------
# PDF OCR
# ---------------------------------------------------------

def _extract_pdf_text(pdf_path):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "PDF support is unavailable in this deployment."
        ) from exc

    doc = None

    try:
        doc = fitz.open(pdf_path)

        if doc.page_count == 0:
            raise RuntimeError(
                "The uploaded PDF contains no pages."
            )

        total_pages = doc.page_count

        page_count = min(
            total_pages,
            PDF_MAX_PAGES
        )

        chunks = []

        for index in range(page_count):

            page = doc.load_page(index)

            pix = page.get_pixmap(
                matrix=fitz.Matrix(
                    PDF_RENDER_SCALE,
                    PDF_RENDER_SCALE
                ),
                alpha=False
            )

            image = Image.frombytes(
                "RGB",
                [pix.width, pix.height],
                pix.samples
            )

            image = _bound_image(
                image,
                OCR_TARGET_DIMENSION
            )

            text = _extract_image_text(
                image,
                source_name=f"PDF page {index + 1}"
            )

            if text:
                chunks.append(
                    f"[PAGE {index + 1}]\n{text}"
                )

        if not chunks:
            raise RuntimeError(
                "OCR found no readable text "
                "in the uploaded PDF."
            )

        if total_pages > PDF_MAX_PAGES:
            chunks.append(
                f"[SYSTEM NOTE] Only the first "
                f"{PDF_MAX_PAGES} pages were processed "
                f"by the prototype."
            )

        return "\n\n".join(chunks)

    except RuntimeError:
        raise

    except Exception as exc:
        raise RuntimeError(
            f"Unable to process PDF: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass


# ---------------------------------------------------------
# MAIN TEXT EXTRACTION
# ---------------------------------------------------------

def extract_text(file_path):

    if not file_path:
        raise RuntimeError(
            "No document path was provided for OCR."
        )

    if not os.path.isfile(file_path):
        raise RuntimeError(
            f"Uploaded document was not found: "
            f"{file_path}"
        )

    ext = os.path.splitext(
        file_path
    )[1].lower()

    # PDF
    if ext == ".pdf":
        return _extract_pdf_text(file_path)

    # IMAGE
    image = _load_image(file_path)

    return _extract_image_text(
        image,
        source_name=os.path.basename(file_path)
    )


# ---------------------------------------------------------
# OPTIONAL OCR TOKEN CONFIDENCE
# ---------------------------------------------------------

def extract_ocr_token_confidence(file_path):
    """Extract OCR token confidence when explicitly enabled.

    Disabled by default because image_to_data() performs
    another complete Tesseract OCR pass.
    """

    if os.environ.get(
        "SKIP_OCR_TOKEN_CONFIDENCE",
        "1"
    ) == "1":
        return []

    image = _load_image(file_path)

    processed = _preprocess_image(image)

    try:
        data = pytesseract.image_to_data(
            processed,
            config="--oem 3 --psm 6",
            output_type=pytesseract.Output.DICT,
            timeout=OCR_TIMEOUT_SECONDS
        )

    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR is not available "
            "in the server runtime."
        ) from exc

    except RuntimeError as exc:
        raise RuntimeError(
            f"OCR token confidence extraction failed: "
            f"{exc}"
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            f"OCR token confidence extraction failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    tokens = []

    texts = data.get(
        "text",
        []
    )

    confidences = data.get(
        "conf",
        []
    )

    for text, confidence in zip(
        texts,
        confidences
    ):
        text = str(text).strip()

        if not text:
            continue

        try:
            confidence_value = float(
                confidence
            )
        except (
            TypeError,
            ValueError
        ):
            continue

        if confidence_value < 0:
            continue

        tokens.append({
            "text": text,
            "confidence": confidence_value
        })

    return tokens