FROM python:3.11-slim

# System deps needed by cryptography / psycopg2 build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy full repo so PYTHONPATH=/app resolves `backend.*` imports
COPY . .

ENV PYTHONPATH=/app

# Run unprivileged. /app/uploads is pre-created so a fresh named volume
# inherits this ownership (an existing root-owned volume needs a one-time chown).
RUN useradd --create-home --uid 10001 app && mkdir -p /app/uploads && chown -R app:app /app
USER app

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
