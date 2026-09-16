"""Fast OCR regression suite for Dhara-Netra AI.
Run locally: python ocr_regression_test.py
"""
from pathlib import Path
import sys,time
from PIL import Image
ROOT=Path(__file__).resolve().parent; DOC=ROOT/'Backend'/'test_documents'
sys.path.insert(0,str(ROOT/'Backend'))
from ocr import extract_text, extract_ocr_token_confidence
from extract_fields import extract_fields

def check(name,ok,detail=''):
    if not ok: raise AssertionError(f'{name}: {detail}')
    print('PASS:',name)

for name,extent in {'01_match_document.png':'1.25 Acres','02_mismatch_area_document.png':'1.20 Acres','03_ocr_review_document.png':'1.25 Acres'}.items():
    p=DOC/name; t=time.time(); text=extract_text(str(p)); dt=time.time()-t
    check(f'OCR {name}',bool(text) and dt<8,f'{dt:.2f}s')
    fields,_=extract_fields(text,str(p))
    check(f'Extraction {name}',fields.get('owner_name')=='Ravi Kumar' and fields.get('survey_number')=='145/2A' and fields.get('extent')==extent and fields.get('assessment_number')=='114-145-022',str(fields))
    check(f'No false handwriting {name}',not fields.get('record_name'))

legacy=DOC/'legacy_handwritten_land_record.jpg'; fields,evidence=extract_fields(extract_text(str(legacy)),str(legacy))
check('Legacy demo transcript',fields.get('owner_name')=='G. Ramesh' and fields.get('survey_number')=='125' and fields.get('extent')=='2.5 Acres')
check('Legacy explicit review mode',bool(evidence) and all(v.get('mode')=='verified_demo_template_transcript' for v in evidence.values()))
check('Optional confidence disabled',extract_ocr_token_confidence(str(DOC/'01_match_document.png'))==[])

# PDF support: one page at a time, bounded rendering.
import fitz
pdf='/tmp/dhara_final_regression.pdf'; src=str(DOC/'sample_land_record_full.png'); doc=fitz.open(); pix=fitz.Pixmap(src); page=doc.new_page(width=pix.width,height=pix.height); page.insert_image(page.rect,filename=src); doc.save(pdf); doc.close()
t=time.time(); text=extract_text(pdf); dt=time.time()-t
check('PDF OCR', 'Government of Andhra Pradesh' in text and 'Duwada' in text and dt<10, f'{dt:.2f}s')

# Oversized/invalid input must fail safely rather than crash the server.
big='/tmp/dhara_big_regression.png'; Image.new('RGB',(5000,5000),'white').save(big)
try: extract_text(big)
except RuntimeError as e: check('Oversized image safe handling','OCR returned no readable text' in str(e))
else: check('Oversized image bounded',True)
bad='/tmp/dhara_bad_regression.bin'; Path(bad).write_bytes(b'not an image')
try: extract_text(bad)
except RuntimeError: check('Invalid file safe handling',True)
else: raise AssertionError('Invalid file unexpectedly processed')

print('ALL FAST OCR REGRESSION CHECKS PASSED')
