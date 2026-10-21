#!/bin/sh
# Runs vault_app.py full screen as a kiosk. If the app crashes it is restarted after a few
# seconds; leaving it normally (the Exit button, which needs the admin PIN if one is set) stops
# it. Anything extra on the command line is passed to vault_app.py, e.g. ./run_vault.sh --mode enrol
#
# The autostart entry (can-you-break-the-bank.desktop.template, see SETUP.md) runs this at login.
# Output goes to vault_app.log in this folder, which is emptied when it passes 1 MB.

cd "$(dirname "$0")" || exit 1
LOG=vault_app.log

while true; do
    if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 1048576 ]; then
        : > "$LOG"
    fi
    .venv/bin/python vault_app.py "$@" >> "$LOG" 2>&1
    status=$?
    [ "$status" -eq 0 ] && exit 0
    echo "$(date '+%Y-%m-%d %H:%M:%S') vault_app.py exited with status $status - restarting in 3 seconds" >> "$LOG"
    sleep 3
done
