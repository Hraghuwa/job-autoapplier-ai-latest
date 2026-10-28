#!/usr/bin/env bash
# One-command self-host: generates secrets, then starts the full stack in Docker.
#   bash setup.sh            → set up (first run) and start
#   docker compose down      → stop      (data is kept in a Docker volume)
# Safe to re-run: existing .env files are never overwritten.
set -euo pipefail
cd "$(dirname "$0")"

command -v docker >/dev/null || { echo "Docker is not installed. Get Docker Desktop: https://www.docker.com/products/docker-desktop/"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is installed but not running. Start Docker Desktop and re-run."; exit 1; }

hex() { openssl rand -hex "$1"; }
fernet() { openssl rand -base64 32 | tr '+/' '-_'; }   # 32 random bytes, url-safe base64 = a valid Fernet key

if [ ! -f .env ]; then
  echo "POSTGRES_PASSWORD=$(hex 16)" > .env
  echo "Created .env (database password)"
fi
# shellcheck disable=SC1091
. ./.env

if [ ! -f backend/.env ]; then
  read -r -p "Gemini API key (free at https://aistudio.google.com/apikey, Enter to skip): " GEMINI || true
  cat > backend/.env <<EOF
DATABASE_URL=postgresql+asyncpg://jobagent:${POSTGRES_PASSWORD}@postgres:5432/jobagent
REDIS_URL=redis://redis:6379/0
SECRET_KEY=$(hex 32)
FERNET_KEY=$(fernet)
SYSTEM_GEMINI_KEY=${GEMINI:-}
FRONTEND_URL=http://localhost:3000
EOF
  echo "Created backend/.env (secrets generated)"
fi

# Containers run as uid 10001; on Linux a bind-mounted dir must be writable by it (resume uploads).
mkdir -p uploads && chmod 777 uploads

echo "Building and starting containers (first run takes 5-10 minutes)..."
docker compose up -d --build

printf "Waiting for the API"
for _ in $(seq 1 90); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo; echo "JobAgent is running: open http://localhost:3000 and register."
    exit 0
  fi
  printf "."; sleep 2
done
echo; echo "API did not come up in 3 minutes. Check logs: docker compose logs backend"; exit 1
