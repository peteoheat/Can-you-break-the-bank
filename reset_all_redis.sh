#!/bin/bash

echo "=== PiFace Redis Reset ==="

# The wipe script lives in the same directory as this one, wherever the project is installed
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Adjust these if your service names differ
SERVICE_1="redis-sync.service"

echo "[1/4] Stopping sync services…"
sudo systemctl stop $SERVICE_1

echo "[2/4] Running wipe script…"
python3 "$SCRIPT_DIR/delete_all_redis_keys.py"
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

