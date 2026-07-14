FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY streamlit_app.py .
COPY app_fastapi.py .
COPY config ./config

EXPOSE 8080

CMD uvicorn app_fastapi:app --host 0.0.0.0 --port "${PORT:-8080}"
