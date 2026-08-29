#!/usr/bin/env bash
# Start the Mininet Topology (requires sudo/root privileges)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=========================================================="
echo " Starting Mininet Topology (1 Client, 1 Switch, 3 Servers)..."
echo " Target Controller: 127.0.0.1:6653"
echo "=========================================================="

# Clean up any leftover mininet state
sudo mn -c 2>/dev/null || true

# Run topology script with root privileges
sudo python3 topology/mininet_topo.py
