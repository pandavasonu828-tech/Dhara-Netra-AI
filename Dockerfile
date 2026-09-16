FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TESSERACT_CMD=/usr/bin/tesseract \
    MAX_OCR_DIMENSION=1400 \
    OCR_TIMEOUT_SECONDS=15 \
    SKIP_OCR_TOKEN_CONFIDENCE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY Backend/requirements.txt /app/Backend/requirements.txt
RUN pip install --no-cache-dir -r /app/Backend/requirements.txt

COPY Backend /app/Backend
COPY Frontend /app/Frontend

RUN mkdir -p /app/Backend/uploads
EXPOSE 10000
CMD ["sh", "-c", "gunicorn --chdir Backend app:app --bind 0.0.0.0:${PORT:-10000} --workers 1 --timeout 120"]
