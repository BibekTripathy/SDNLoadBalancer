#!/usr/bin/env bash
# TCP Congestion Control Lab - one short real-traffic experiment in Mininet.
# Usage:
#   scripts/run_tcp_lab_smoke.sh                     # dumbbell, OVS standalone
#   scripts/run_tcp_lab_smoke.sh --controller ryu    # dumbbell, Ryu on :6653
#   scripts/run_tcp_lab_smoke.sh --target vip        # client -> VIP 10.0.0.100 (LB Ryu running,
#                                                    #  the LB Mininet from run_mininet.sh stopped)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=========================================================="
echo " TCP Lab smoke test (Linux reno, SACK off) $*"
echo "=========================================================="

# Mininet must run as root with the system Python (which has the mininet package)
sudo python3 -m tcp_lab.mininet.smoke_test "$@"

# Give the results back to the normal user
sudo chown -R "$(id -u):$(id -g)" results 2>/dev/null || true
