#!/usr/bin/env bash
# Start the React SDN Load Balancer Frontend Dashboard
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT/front-end"

echo "=========================================================="
echo " Starting SDN Load Balancer Frontend Dashboard..."
echo " URL: http://localhost:3000"
echo "=========================================================="

npm run dev
