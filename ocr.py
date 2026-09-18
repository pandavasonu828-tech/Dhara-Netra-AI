from PIL import Image
import pytesseract
import os


# ---------------------------------------------------------
# TESSERACT CONFIGURATION
# ---------------------------------------------------------

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# On your local Windows computer, use the path above if it exists.
# On Render/Linux, this path will not exist, so pytesseract will
# use the Tesseract executable installed in the container PATH.
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


# ---------------------------------------------------------
# OCR IMAGE SIZE
# ---------------------------------------------------------

# Keep the image reasonably small so OCR does not consume
# too much CPU/RAM on the Render server.
MAX_OCR_DIMENSION = 1400


def _load_ocr_image(image_path):
    """
    Load the uploaded image and resize it only when necessary.

    We keep the aspect ratio unchanged so that text such as
    survey numbers and IDs is not distorted.
    """

    image = Image.open(image_path).convert("RGB")

    longest = max(image.size)

    if longest > MAX_OCR_DIMENSION:
        scale = MAX_OCR_DIMENSION / float(longest)

        size = (
            max(1, int(image.width * scale)),
            max(1, int(image.height * scale)),
        )

        image = image.resize(
            size,
            Image.Resampling.LANCZOS
        )

    return image


# ---------------------------------------------------------
# PREPROCESS IMAGE
# ---------------------------------------------------------

def preprocess_image(image_path):
    """
    Convert the image to grayscale.

    This function is kept because other parts of the
    application may use it.
    """

    image = _load_ocr_image(image_path)

    return image.convert("L")


# ---------------------------------------------------------
# MAIN OCR FUNCTION
# ---------------------------------------------------------

def extract_text(image_path):
    """
    Extract text from the uploaded land-record image.

    First attempt:
        - Normal RGB image
        - PSM 6
        - Maximum 18 seconds

    If that takes too long:
        - Smaller image
        - Grayscale
        - PSM 6
        - Maximum 8 seconds

    This prevents OCR from getting stuck indefinitely
    while still giving it enough time on Render.
    """

    # -------------------------------
    # FIRST OCR ATTEMPT
    # -------------------------------

    image = _load_ocr_image(image_path)

    try:
        text = pytesseract.image_to_string(
            image,
            lang="eng",
            config="--psm 6",
            timeout=18,
        ).strip()

        # If OCR successfully produced text, return it.
        if text:
            return text

    except (RuntimeError, pytesseract.TesseractError):
        # The first OCR attempt can fail because of a timeout
        # or a Tesseract processing error.
        pass


    # -------------------------------
    # FALLBACK OCR ATTEMPT
    # -------------------------------

    try:
        # Make a smaller copy for the fallback attempt.
        fallback = image.copy()

        fallback.thumbnail(
            (1000, 1000),
            Image.Resampling.LANCZOS
        )

        # Convert to grayscale.
        fallback = fallback.convert("L")

        text = pytesseract.image_to_string(
            fallback,
            lang="eng",
            config="--psm 6",
            timeout=8,
        ).strip()

        return text

    except (RuntimeError, pytesseract.TesseractError):
        # If both attempts fail, return an empty string.
        #
        # The rest of the application can then correctly
        # mark the fields as NEEDS REVIEW instead of crashing.
        return ""


# ---------------------------------------------------------
# OCR CONFIDENCE
# ---------------------------------------------------------

def extract_ocr_token_confidence(image_path):
    """
    Return lightweight OCR evidence.

    IMPORTANT:
    We intentionally do NOT call pytesseract.image_to_data()
    here.

    image_to_data() would launch another complete OCR
    operation and can make the Render server timeout.

    The main extract_text() function already performs OCR,
    so this function remains lightweight.
    """

    return []