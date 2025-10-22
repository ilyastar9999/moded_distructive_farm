#!/bin/sh

# Get port from config.py
PORT=$(python3 -c "from config import CONFIG; print(CONFIG.get('SYSTEM_PORT'))")
WEB_PORT=$(python3 -c "from config import CONFIG; print(CONFIG.get('PORT'))")

# Build and run docker with port forwarding
if [ "$1" = "--build" ]; then
    docker build -t pb_farm .
fi

docker run --rm -p $PORT:$PORT pb_farm
