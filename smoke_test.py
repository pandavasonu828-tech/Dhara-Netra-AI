"""
Static smoke checks for Dhara-Netra AI deployment configuration.
Run: python smoke_test.py
"""
from pathlib import Path
import ast, re

ROOT = Path(__file__).resolve().parent
app = (ROOT / "Backend" / "app.py").read_text(encoding="utf-8")
docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
ocr = (ROOT / "Backend" / "ocr.py").read_text(encoding="utf-8")
js = (ROOT / "Frontend" / "script.js").read_text(encoding="utf-8")

ast.parse(app)
ast.parse(ocr)

assert 'port = int(os.environ.get("PORT", "5000"))' in app
assert 'app.run(host="0.0.0.0", port=port, debug=True)' in app
assert "0.0.0.0:${PORT:-10000}" in docker
assert "tesseract-ocr" in docker
assert "PyMuPDF" in (ROOT / "Backend" / "requirements.txt").read_text(encoding="utf-8")
assert "PDF_MAX_PAGES=3" in docker
assert 'TESSERACT_CMD=/usr/bin/tesseract' in docker
assert 'window.location.origin' in js
assert "application/pdf" in js
assert "127.0.0.1:5000" in js  # only retained for file:// local development

print("PASS: Python syntax/configuration")
print("PASS: Docker Tesseract + Render binding")
print("PASS: Frontend hosted API uses window.location.origin")
print("Dhara-Netra AI deployment smoke checks passed.")
