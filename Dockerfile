FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY streamlit_app.py .
COPY config ./config

EXPOSE 8080

CMD if [ -n "$STREAMLIT_BASE_URL_PATH" ]; then \
      streamlit run streamlit_app.py \
        --server.port="${PORT:-8080}" \
        --server.address=0.0.0.0 \
        --server.headless=true \
        --server.enableCORS=false \
        --server.enableXsrfProtection=false \
        --server.baseUrlPath="$STREAMLIT_BASE_URL_PATH"; \
    else \
      streamlit run streamlit_app.py \
        --server.port="${PORT:-8080}" \
        --server.address=0.0.0.0 \
        --server.headless=true \
        --server.enableCORS=false \
        --server.enableXsrfProtection=false; \
    fi
