FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Кириличні шрифти для ідеального рендеру української (і, ї, є, ґ), російської та білоруської (ў) мов
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-core \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .

CMD ["python", "run_polling.py"]
