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
FRONTEND_RUN="/tmp/jafrontend"
DB_DIR="/tmp/jadb"
BACKEND_LOG="/tmp/backend.log"
FRONTEND_LOG="/tmp/frontend.log"

echo "╔══════════════════════════════════════════╗"
echo "║      JobAgent  —  Starting servers       ║"
echo "╚══════════════════════════════════════════╝"

# ── Kill any existing processes ─────────────────────────
echo "→ Cleaning up old processes..."
pkill -9 -f "uvicorn backend.main" 2>/dev/null || true
pkill -9 -f "next-server"          2>/dev/null || true
pkill -9 -f "next dev"             2>/dev/null || true
sleep 1

# ── Ensure DB directory ──────────────────────────────────
mkdir -p "$DB_DIR"

# ── Seed DB if missing ───────────────────────────────────
if [ ! -f "$DB_DIR/jobagent.db" ]; then
  echo "→ Creating database..."
  python3 << PYEOF
import sqlite3, uuid
from passlib.context import CryptContext
pwd = CryptContext(schemes=['bcrypt'], deprecated='auto').hash('JobAgent@2024')
uid = str(uuid.uuid4()).replace('-','')
conn = sqlite3.connect('$DB_DIR/jobagent.db')
# Create all tables (SQLAlchemy will add any missing ones on startup)
conn.executescript("""
CREATE TABLE IF NOT EXISTS users (
  id CHAR(32) PRIMARY KEY, email VARCHAR(255) UNIQUE NOT NULL,
  hashed_password VARCHAR(255) NOT NULL, name VARCHAR(255) NOT NULL,
  plan VARCHAR(4) NOT NULL DEFAULT 'free', is_admin BOOLEAN NOT NULL DEFAULT 0,
  gemini_key_encrypted VARCHAR(512), tokens_used_today INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS user_profiles (
  id CHAR(32) PRIMARY KEY, user_id CHAR(32) UNIQUE,
  resume_url TEXT, resume_hash TEXT, resume_filename TEXT,
  extracted_data TEXT, job_preferences TEXT, autofill_bank TEXT,
  cover_letter TEXT, platform_passwords TEXT, session_cookies TEXT,
  chrome_profile_path TEXT, fingerprint TEXT,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS applications (
  id CHAR(32) PRIMARY KEY, user_id CHAR(32), platform TEXT,
  job_title TEXT, company TEXT, location TEXT, job_url TEXT,
  jd_text TEXT, job_hash TEXT, source_url TEXT, match_score INTEGER,
  match_reason TEXT, matched_skills TEXT, missing_skills TEXT,
  status TEXT DEFAULT 'applied', cover_letter_used TEXT,
  interview_prep TEXT, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS job_outcomes (
  id CHAR(32) PRIMARY KEY, application_id CHAR(32) UNIQUE,
  outcome TEXT, outcome_updated_at DATETIME,
  jd_keywords TEXT, resume_skills TEXT);
CREATE TABLE IF NOT EXISTS agent_runs (
  id CHAR(32) PRIMARY KEY, user_id CHAR(32), phase INTEGER, platform TEXT,
  celery_task_id TEXT, status TEXT DEFAULT 'queued',
  started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME, applied_count INTEGER DEFAULT 0,
  skipped_count INTEGER DEFAULT 0, error_count INTEGER DEFAULT 0,
  config_snapshot TEXT);
CREATE TABLE IF NOT EXISTS agent_logs (
  id CHAR(32) PRIMARY KEY, run_id CHAR(32), application_id CHAR(32),
  event_type TEXT, message TEXT, screenshot_url TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS usage_quotas (
  id CHAR(32) PRIMARY KEY, user_id CHAR(32), platform TEXT, quota_date DATE,
  applies_count INTEGER DEFAULT 0, tokens_used INTEGER DEFAULT 0,
  UNIQUE(user_id, platform, quota_date));
CREATE TABLE IF NOT EXISTS payments (
  id CHAR(32) PRIMARY KEY, user_id CHAR(32), razorpay_order_id TEXT,
  razorpay_payment_id TEXT, amount INTEGER, currency TEXT DEFAULT 'INR',
  plan TEXT, plan_period TEXT, credits_purchased INTEGER,
  status TEXT DEFAULT 'created', created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS notifications (
  id CHAR(32) PRIMARY KEY, user_id CHAR(32), type TEXT, title TEXT,
  body TEXT, read INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS referrals (
  id CHAR(32) PRIMARY KEY, referrer_id CHAR(32), referred_id CHAR(32),
  code TEXT UNIQUE, status TEXT DEFAULT 'pending', rewarded_at DATETIME);
""")
conn.execute("INSERT OR IGNORE INTO users VALUES (?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
  (uid,'hraghuwanshi3110@gmail.com',pwd,'Harsh Raghuwanshi','pro',1,None,0))
pid = str(uuid.uuid4()).replace('-','')
conn.execute("INSERT OR IGNORE INTO user_profiles VALUES (?,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,datetime('now'))",
  (pid, uid))
conn.execute("INSERT OR IGNORE INTO referrals VALUES (?,?,NULL,'HARSH2024','pending',NULL)",
  (str(uuid.uuid4()).replace('-',''), uid))
conn.commit()
print("  DB seeded with admin user")
conn.close()
PYEOF
fi

# ── Sync frontend to fast /tmp filesystem ─────────────────
echo "→ Syncing frontend to /tmp for faster I/O..."
mkdir -p "$FRONTEND_RUN"
# Using rsync -a to preserve symlinks and be efficient
rsync -a --exclude='.next' --exclude='.git' "$FRONTEND_SRC/" "$FRONTEND_RUN/"

# ── Start Backend ────────────────────────────────────────
echo "→ Starting Backend (FastAPI on :8000)..."
cd "$BACKEND_DIR"
export PYTHONPATH="$BACKEND_DIR"
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > "$BACKEND_LOG" 2>&1 &
BPID=$!

# Wait for backend health
echo -n "  Waiting for backend"
for i in $(seq 1 20); do
  if curl -sm 1 http://localhost:8000/health > /dev/null 2>&1; then
    echo " ✅"
    break
  fi
  echo -n "."
  sleep 1
done

# ── Start Frontend ───────────────────────────────────────
echo "→ Starting Frontend (Next.js on :3000)..."
cd "$FRONTEND_RUN"
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
echo "║  Backend:   http://localhost:8000        ║"
echo "║  API Docs:  http://localhost:8000/docs   ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Login:  hraghuwanshi3110@gmail.com      ║"
echo "║  Pass:   JobAgent@2024                   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Logs: tail -f $BACKEND_LOG"
echo "      tail -f $FRONTEND_LOG"
