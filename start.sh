#!/bin/bash
# ══════════════════════════════════════════════════════════
#  JobAgent — Single-command startup script
#  Starts both Backend (FastAPI:8000) + Frontend (Next.js:3000)
#  Usage: bash start.sh
# ══════════════════════════════════════════════════════════
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/.venv" ]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
fi
BACKEND_DIR="$SCRIPT_DIR"
FRONTEND_SRC="$SCRIPT_DIR/frontend"

# ── Load NVM if present ──────────────────────────────────
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

FRONTEND_RUN="/tmp/jafrontend"
DB_DIR="/tmp/jadb"
BACKEND_LOG="/tmp/backend.log"
FRONTEND_LOG="/tmp/frontend.log"

echo "╔══════════════════════════════════════════╗"
echo "║      JobAgent  —  Starting servers       ║"
echo "╚══════════════════════════════════════════╝"

# ── Ensure .env exists ──────────────────────────────────
if [ ! -f "$BACKEND_DIR/backend/.env" ]; then
  echo "→ Generating backend/.env with keys..."
  S_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  F_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  cat << EOF > "$BACKEND_DIR/backend/.env"
SECRET_KEY=$S_KEY
ALGORITHM=HS256
FERNET_KEY=$F_KEY
DATABASE_URL=sqlite+aiosqlite:///$DB_DIR/jobagent.db
REDIS_URL=redis://localhost:6379/0
EOF
fi

# ── Kill any existing processes ─────────────────────────
echo "→ Cleaning up old processes..."
pkill -9 -f "uvicorn backend.main"           2>/dev/null || true
pkill -9 -f "next-server"                    2>/dev/null || true
pkill -9 -f "next dev"                        2>/dev/null || true
# Kill stale Celery workers too — otherwise every ./start.sh leaves the old
# worker(s) running. They pile up (24 seen in the wild), share one node name
# (DuplicateNodename), and stale ones (old code / old DB) grab the run and can't
# find it → the mission sits QUEUED forever with 0 output.
pkill -9 -f "celery -A backend.workers.celery_app" 2>/dev/null || true
pkill -9 -f "celery_app worker"               2>/dev/null || true
sleep 1

# ── Ensure DB directory ──────────────────────────────────
mkdir -p "$DB_DIR"

# ── Pin DB + seed (model-based schema, always correct for sqlite & Postgres) ─
# Export DATABASE_URL so the seed, backend, and worker all use the SAME db.
export DATABASE_URL="sqlite+aiosqlite:///$DB_DIR/jobagent.db"
echo "→ Seeding database (full schema from models + admin)..."
python3 "$SCRIPT_DIR/scripts/seed_local.py" || echo "  ⚠️  seed failed (see above)"

# ── Start servers directly from source (faster local dev) ─────────────────
echo "→ Preparing startup from source..."

# ── Ensure Redis is running ──────────────────────────────
echo "→ Checking Redis..."
if ! redis-cli ping > /dev/null 2>&1; then
  echo "  ⚠️  Redis is NOT running. Attempting to start..."
  if command -v redis-server > /dev/null 2>&1; then
    redis-server --daemonize yes
    sleep 2
    if redis-cli ping > /dev/null 2>&1; then
      echo "  ✅ Redis started successfully."
    else
      echo "  ❌ Failed to start Redis. Agent tasks will fail."
    fi
  else
    echo "  ❌ redis-server not found. Please install redis."
  fi
else
  echo "  ✅ Redis is already running."
fi

# ── Ensure the agent browser deps are present ────────────
# The worker (and the in-thread fallback) import selenium; without it every run
# dies "No module named 'selenium'". Self-heal here so a restart always fixes it.
echo "→ Ensuring agent deps (selenium, webdriver-manager)..."
python3 -c "import selenium" 2>/dev/null || python3 -m pip install -q -r "$SCRIPT_DIR/requirements-agents.txt"

# ── Start Backend ────────────────────────────────────────
echo "→ Starting Backend (FastAPI on :3002)..."
cd "$BACKEND_DIR"
export PYTHONPATH="$BACKEND_DIR"
# Pin backend + worker to the SAME db we seeded above. A pre-existing
# backend/.env may point at a different file (e.g. backend.db) whose admin
# password doesn't match the banner creds → login 401s. An env var overrides
# the .env file, so backend, worker, and the seed always agree.
export DATABASE_URL="sqlite+aiosqlite:///$DB_DIR/jobagent.db"
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 3002 > "$BACKEND_LOG" 2>&1 &

echo "→ Starting Celery Worker..."
python3 -m celery -A backend.workers.celery_app worker --loglevel=info -Q agents,default > /tmp/worker.log 2>&1 &

BPID=$!

# Wait for backend health
echo -n "  Waiting for backend"
for i in $(seq 1 20); do
  if curl -sm 1 http://localhost:3002/health > /dev/null 2>&1; then
    echo " ✅"
    break
  fi
  echo -n "."
  sleep 1
done

# ── Start Frontend ───────────────────────────────────────
# Point the frontend at the SAME port the backend is started on above (3002).
# A stale frontend/.env.local (e.g. :8000 from an older setup) makes login fail
# with "Can't reach the API at http://localhost:8000 / Network Error". Enforce
# the correct ports every launch so the local stack is always self-consistent.
echo "→ Aligning frontend API URL to backend (:3002)..."
printf 'NEXT_PUBLIC_API_URL=http://localhost:3002\nNEXT_PUBLIC_WS_URL=ws://localhost:3002\n' > "$FRONTEND_SRC/.env.local"

echo "→ Starting Frontend (Next.js on :3000)..."
cd "$FRONTEND_SRC"
# Using npx next dev for reliable binary execution
npx next dev --port 3000 > "$FRONTEND_LOG" 2>&1 &
FPID=$!

# Wait for "Ready"
echo -n "  Waiting for frontend"
for i in $(seq 1 30); do
  if grep -q "Ready in" "$FRONTEND_LOG" 2>/dev/null; then
    echo " ✅"
    break
  fi
  echo -n "."
  sleep 1
done

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         ✅  JobAgent is LIVE             ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Frontend:  http://localhost:3000        ║"
echo "║  Backend:   http://localhost:3002        ║"
echo "║  API Docs:  http://localhost:3002/docs   ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Login:  hraghuwanshi3110@gmail.com      ║"
echo "║  Pass:   JobAgent@2024                   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Logs: tail -f $BACKEND_LOG"
echo "      tail -f $FRONTEND_LOG"
