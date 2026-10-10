#!/usr/bin/env bash
set -e

echo "=========================================="
echo " Starting Open vSwitch..."
echo "=========================================="
service openvswitch-switch start

echo "=========================================="
echo " Starting API Gateway on port 8000..."
echo "=========================================="
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

echo "=========================================="
echo " Starting Ryu Controller on port 6653..."
echo "=========================================="
python3 scripts/ryu_manager.py controller.app --ofp-tcp-listen-port 6653 &
RYU_PID=$!

echo "Waiting for services to initialize..."
sleep 3

echo "=========================================="
echo " Starting Mininet Topology..."
echo "=========================================="
# Run mininet topology script (it spawns the servers as well)
python3 topology/mininet_topo.py

# Mininet script opens CLI(). When that exits, we should kill the background processes.
kill $API_PID $RYU_PID 2>/dev/null
