#!/usr/bin/env bash
# TCP Congestion Control Lab - scenarios S3-S6 with real Linux TCP in Mininet.
# Usage:
#   scripts/run_tcp_lab_mininet.sh                          # S3-S6, 3 runs per variant
#   scripts/run_tcp_lab_mininet.sh --scenario S3 --runs 5
#   scripts/run_tcp_lab_mininet.sh --scenario S4 --variant 2_flows
#   scripts/run_tcp_lab_mininet.sh --controller ryu         # dumbbell switches under Ryu
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=========================================================="
echo " TCP Lab Mininet scenarios (Linux reno, SACK off) $*"
echo "=========================================================="

# Mininet must run as root with the system Python (which has the mininet package)
sudo python3 -m tcp_lab.run_mininet_scenarios "$@"

# Give the results back to the normal user
sudo chown -R "$(id -u):$(id -g)" results 2>/dev/null || true
