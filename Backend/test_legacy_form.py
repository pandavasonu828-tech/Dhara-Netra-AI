from ocr import extract_text
from extract_fields import extract_fields

path = "test_documents/legacy_handwritten_land_record.jpg"
fields, evidence = extract_fields(extract_text(path), path)
print("=== LEGACY HANDWRITTEN FORM TEST ===")
for key, value in fields.items():
    print(f"{key}: {value}")
print("\n=== EXTRACTION MODES ===")
for key, value in evidence.items():
    print(f"{key}: {value['mode']} | raw OCR: {value.get('raw_ocr','')}")
