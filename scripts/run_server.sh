#!/bin/bash
MODE=$1
if [ "$MODE" != "handson" ] && [ "$MODE" != "solution" ]; then
    echo "Usage: ./scripts/run_server.sh [handson|solution]"
    exit 1
fi

# Set active mode
echo "$MODE" > .active_mode

# Kill existing demo processes
pkill -f run_demo.py || true

# Start the demo
python run_demo.py
