#!/usr/bin/env python3
"""
delete_all_redis_keys.py

Deletes all keys on local and remote Redis instances.
Now supports command-line flags:

  --stop-service yes|no
  --start-service yes|no

Defaults:
  --stop-service no
  --start-service no
"""

import os
import sys
import time
import subprocess
import argparse
import redis


# ---------------------------------------------------------------------
# Configuration (same defaults as previous script)
# ---------------------------------------------------------------------
LOCAL_REDIS_HOST = os.environ.get("LOCAL_REDIS_HOST", "127.0.0.1")
LOCAL_REDIS_PORT = int(os.environ.get("LOCAL_REDIS_PORT", "6379"))
LOCAL_REDIS_DB = int(os.environ.get("LOCAL_REDIS_DB", "0"))
LOCAL_REDIS_PASS = os.environ.get("LOCAL_REDIS_PASS", None)

REMOTE_REDIS_HOST = os.environ.get("REMOTE_REDIS_HOST", "192.168.8.152")
REMOTE_REDIS_PORT = int(os.environ.get("REMOTE_REDIS_PORT", "6379"))
REMOTE_REDIS_DB = int(os.environ.get("REMOTE_REDIS_DB", "0"))
REMOTE_REDIS_PASS = os.environ.get("REMOTE_REDIS_PASS", None)

SERVICE_NAME = os.environ.get("SERVICE_NAME", "redis-sync.service")

SCAN_COUNT = 500
DEL_BATCH = 200


# ---------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------
def redis_conn(host, port, db, password):
    return redis.Redis(host=host, port=port, db=db, password=password, decode_responses=False)


def server_info(r):
    try:
        info = r.info()
        role = info.get("role", "unknown")
        dbsize = r.dbsize()
        return role, dbsize, info
    except Exception as e:
        return "error", None, {"error": str(e)}


def scan_and_delete(r, name):
    deleted = 0
    cursor = 0
    to_delete = []

    print(f"[info] SCAN+DEL fallback on {name}...")

    while True:
        try:
            cursor, keys = r.scan(cursor=cursor, count=SCAN_COUNT)
        except Exception as e:
            print(f"[error] SCAN failed on {name}: {e}")
            break

        if keys:
            to_delete.extend(keys)

        # batch deletion
        while len(to_delete) >= DEL_BATCH:
            batch = to_delete[:DEL_BATCH]
            try:
                r.delete(*batch)
                deleted += len(batch)
            except Exception:
                for k in batch:
                    try:
                        r.delete(k)
                        deleted += 1
                    except Exception:
                        pass
            to_delete = to_delete[DEL_BATCH:]

        if cursor == 0:
            break

    # final batch
    if to_delete:
        try:
            r.delete(*to_delete)
            deleted += len(to_delete)
        except Exception:
            for k in to_delete:
                try:
                    r.delete(k)
                    deleted += 1
                except Exception:
                    pass

    return deleted


def flush_or_scan_delete(r, name):
    role, dbsize, info = server_info(r)
    print(f"[info] {name} role={role}, pre-delete keys={dbsize}")

    if role in ("slave", "replica"):
        print(f"[warn] {name} is a replica → using SCAN+DEL instead of FLUSHDB.")
        return scan_and_delete(r, name)

    try:
        print(f"[info] FLUSHDB on {name}...")
        r.flushdb()
        time.sleep(0.1)
        if r.dbsize() == 0:
            print(f"[ok] FLUSHDB succeeded on {name}.")
            return 0
        else:
            print(f"[warn] FLUSHDB incomplete; falling back to SCAN+DEL.")
            return scan_and_delete(r, name)
    except Exception as e:
        print(f"[warn] FLUSHDB failed on {name}: {e}")
        return scan_and_delete(r, name)


def verify_empty(r, name):
    try:
        if r.dbsize() == 0:
            print(f"[ok] Verified {name} is empty.")
            return True
        else:
            print(f"[error] {name} still has keys!")
            return False
    except Exception as e:
        print(f"[error] Could not verify {name}: {e}")
        return False


# ---------------------------------------------------------------------
# Service control
# ---------------------------------------------------------------------
def stop_service():
    print(f"[info] Stopping service: {SERVICE_NAME} ...")
    try:
        subprocess.run(["sudo", "systemctl", "stop", SERVICE_NAME], check=True)
        print("[info] Service stopped.")
    except Exception as e:
        print(f"[warn] Unable to stop service: {e}")


def start_service():
    print(f"[info] Starting service: {SERVICE_NAME} ...")
    try:
        subprocess.run(["sudo", "systemctl", "start", SERVICE_NAME], check=True)
        print("[info] Service restarted.")
    except Exception as e:
        print(f"[warn] Unable to start service: {e}")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Delete all keys on local and remote Redis with optional service stop/start.")
    parser.add_argument("--stop-service", choices=["yes", "no"], default="no",
                        help="Stop redis-sync service before deletion.")
    parser.add_argument("--start-service", choices=["yes", "no"], default="no",
                        help="Start redis-sync service after deletion.")

    args = parser.parse_args()

    # optional service stop
    if args.stop_service == "yes":
        stop_service()

    local = redis_conn(LOCAL_REDIS_HOST, LOCAL_REDIS_PORT, LOCAL_REDIS_DB, LOCAL_REDIS_PASS)
    remote = redis_conn(REMOTE_REDIS_HOST, REMOTE_REDIS_PORT, REMOTE_REDIS_DB, REMOTE_REDIS_PASS)

    # connectivity check
    for name, r in (("LOCAL", local), ("REMOTE", remote)):
        try:
            r.ping()
        except Exception as e:
            print(f"[error] Cannot connect to {name} Redis: {e}")
            sys.exit(1)

    flush_or_scan_delete(local, "LOCAL")
    flush_or_scan_delete(remote, "REMOTE")

    ok_local = verify_empty(local, "LOCAL")
    ok_remote = verify_empty(remote, "REMOTE")

    if not (ok_local and ok_remote):
        print("[error] Not all databases are empty.")
        if args.start_service == "yes":
            start_service()
        sys.exit(2)

    print("[done] Both Redis instances empty.")

    if args.start_service == "yes":
        start_service()


if __name__ == "__main__":
    main()

