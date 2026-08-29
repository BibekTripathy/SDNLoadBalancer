#!/usr/bin/env bash
# Start the FastAPI REST & WebSocket API Gateway
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

if [ -f ".venv/bin/uvicorn" ]; then
    UVICORN_EXEC=".venv/bin/uvicorn"
else
    UVICORN_EXEC="uvicorn"
fi

echo "=========================================================="
echo " Starting FastAPI & WebSocket Gateway..."
echo " Server URL: http://0.0.0.0:8000"
echo " API Docs:   http://0.0.0.0:8000/docs"
echo " WebSocket:  ws://0.0.0.0:8000/ws/events"
echo "=========================================================="

exec "$UVICORN_EXEC" api.main:app --host 0.0.0.0 --port 8000 --reload
