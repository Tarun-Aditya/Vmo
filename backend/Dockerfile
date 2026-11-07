FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
# pandoc + LibreOffice render the pilot corpus (Word / PDF) and export .docx; poppler reads PDFs; tesseract OCRs scanned ones
RUN apt-get update && apt-get install -y --no-install-recommends pandoc poppler-utils tesseract-ocr libreoffice-writer fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .
EXPOSE 8000
