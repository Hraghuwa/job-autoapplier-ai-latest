#!/bin/bash
# 🤖 Job Auto-Applier worker script

# Get current dir
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$( cd "$DIR/../.." && pwd )"

cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR"

echo "→ Starting Celery Worker (Queue: agents, default)..."
python3 -m celery -A backend.workers.celery_app worker --loglevel=info -Q agents,default
