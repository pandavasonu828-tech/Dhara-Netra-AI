from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract
import os

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def preprocess_image(image_path):
    image = Image.open(image_path).convert("RGB")
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    gray = ImageEnhance.Contrast(gray).enhance(1.25)
    return gray


def extract_text(image_path):
    # IMPORTANT: OCR the original scan first. Strong contrast/median filtering
    # can turn characters such as letter "A" into the digit "4" in survey IDs
    # (e.g. 145/2A -> 145/24). The original image preserves those characters.
    image = Image.open(image_path).convert("RGB")
    return pytesseract.image_to_string(image, config="--psm 6")


def extract_ocr_token_confidence(image_path):
    # Keep confidence measurements tied to the same OCR pass used for fields.
    image = Image.open(image_path).convert("RGB")
    data = pytesseract.image_to_data(image, config="--psm 6", output_type=pytesseract.Output.DICT)
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
