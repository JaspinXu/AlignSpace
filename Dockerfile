FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALIGNSPACE_DB_PATH=/app/data/alignspace.db \
    ALIGNSPACE_UPLOAD_DIR=/app/data/uploads

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY schemas ./schemas
RUN mkdir -p /app/data/uploads && chown -R 10001:10001 /app

USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

