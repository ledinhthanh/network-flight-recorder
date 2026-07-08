#!/bin/bash
set -e
cd /opt/nfr

echo "Pulling latest..."
git pull 2>/dev/null || echo "No git - manual upgrade"

echo "Restarting service..."
systemctl restart nfr.service

echo "Running tests..."
PYTHONPATH=/opt/nfr python3 -m unittest discover tests 2>&1 | tail -5

echo "Upgrade complete."
