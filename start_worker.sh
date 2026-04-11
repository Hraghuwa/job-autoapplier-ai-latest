#!/bin/bash
# 🤖 JobAgent — Worker Startup Helper
# Use this if you want to run the background agent separately from the web servers.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/.venv" ]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
fi

export PYTHONPATH="$SCRIPT_DIR"

echo "🔥 Starting JobAgent Celery Worker..."
echo "Broker: redis://localhost:6379/0"
echo "Queues: agents, default"

python3 -m celery -A backend.workers.celery_app worker --loglevel=info -Q agents,default
