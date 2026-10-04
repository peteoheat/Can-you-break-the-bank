#!/bin/bash

echo "=== PiFace Redis Reset ==="

# Adjust these if your service names differ
SERVICE_1="sync-redis.service"

echo "[1/4] Stopping sync services…"
sudo systemctl stop $SERVICE_1

echo "[2/4] Running wipe script…"
python3 /home/pi/PiFace/delete_all_redis_keys.py
RESULT=$?

if [ $RESULT -ne 0 ]; then
    echo "[FAILED] Redis cleanup did not complete successfully."
    echo "Exit code: $RESULT"
    echo "Services will NOT be restarted."
    exit 1
fi

echo "[3/4] Restarting sync services…"
sudo systemctl start $SERVICE_1

echo "[4/4] Done!"
echo "All Redis keys cleared and sync service restarted successfully."

