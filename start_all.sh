#!/usr/bin/env bash

# This script starts the entire SDN Load Balancer stack:
# Frontend, API Gateway, Ryu Controller, and Mininet Topology.

# Trap SIGINT and SIGTERM to kill all background jobs when the script exits
trap 'echo -e "\nStopping all services..."; kill $(jobs -p) 2>/dev/null; sudo mn -c 2>/dev/null' EXIT

echo "Starting Frontend..."
./scripts/run_frontend.sh > /tmp/sdn_frontend.log 2>&1 &

echo "Starting API Gateway..."
./scripts/run_api.sh > /tmp/sdn_api.log 2>&1 &

echo "Starting Ryu Controller..."
./scripts/run_ryu.sh > /tmp/sdn_ryu.log 2>&1 &

echo "Waiting for services to initialize..."
sleep 3

echo "=========================================================="
echo " All background services started!"
echo " Frontend:  http://localhost:3000"
echo " API Docs:  http://localhost:8000/docs"
echo " Logs are being written to /tmp/sdn_*.log"
echo "=========================================================="
echo "Starting Mininet (this requires your sudo password)..."
echo "Type 'exit' in the Mininet CLI to stop all services."
echo "=========================================================="

# Run Mininet in the foreground
./scripts/run_mininet.sh
