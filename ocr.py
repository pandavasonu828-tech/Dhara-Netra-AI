from PIL import Image
import pytesseract
import os

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# Keep OCR bounded for small cloud instances. Tesseract's word-level
# image_to_data pass is significantly more expensive than image_to_string,
# so the prototype uses the text OCR pass for extraction and does not run a
# second full OCR pass just to calculate token confidence.
MAX_OCR_DIMENSION = 1800

def _load_ocr_image(image_path):
    image = Image.open(image_path).convert("RGB")
    longest = max(image.size)
    if longest > MAX_OCR_DIMENSION:
        scale = MAX_OCR_DIMENSION / float(longest)
        size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image

def preprocess_image(image_path):
    image = _load_ocr_image(image_path)
    return image.convert("L")

def extract_text(image_path):
    # OCR the original scan first. Avoid aggressive filtering because it can
    # change characters such as A -> 4 in survey IDs (145/2A -> 145/24).
    image = _load_ocr_image(image_path)
    return pytesseract.image_to_string(
        image,
        lang="eng",
        config="--psm 6",
        timeout=25,
    ).strip()

def extract_ocr_token_confidence(image_path):
    """Return lightweight OCR evidence without launching a second Tesseract pass.

    The previous implementation called image_to_data() after image_to_string().
    On Render Free this second full Tesseract invocation could exceed the worker
    timeout and kill the request. The extraction pipeline now uses the first OCR
    pass only; confidence.py treats an empty token list as neutral OCR evidence.
    """
    return []
