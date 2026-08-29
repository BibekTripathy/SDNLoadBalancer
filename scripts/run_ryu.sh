#!/usr/bin/env bash
# Start the Ryu SDN Load Balancer Controller with OpenFlow 1.3
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

if [ -f ".venv/bin/python" ]; then
    PYTHON_EXEC=".venv/bin/python"
else
    PYTHON_EXEC="python3"
fi

echo "=========================================================="
echo " Starting SDN Load Balancer Ryu Controller..."
echo " Listening for OpenFlow switches on port 6653..."
echo "=========================================================="

exec "$PYTHON_EXEC" scripts/ryu_manager.py controller.app --ofp-tcp-listen-port 6653 --verbose
