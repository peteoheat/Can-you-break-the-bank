#!/usr/bin/env python3
import redis
import sys
from app_config import load_config

# ==== Configuration ====
# Hosts and ports come from ~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg
config = load_config()
LOCAL_REDIS_HOST = config["local_host"]
LOCAL_REDIS_PORT = config["local_port"]

REMOTE_REDIS_HOST = config["remote_host"]  # None in single node mode
REMOTE_REDIS_PORT = config["remote_port"]
# =======================


def redis_conn(host, port):
    """Return a Redis connection without decoding errors."""
    return redis.Redis(host=host, port=port, decode_responses=False)


def decode_safe(value):
    """Decode bytes safely for display."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except:
            return f"<binary:{value.hex()}>"
    return value


def print_key_value(r, key):
    """Detect key type and print its value."""
    key_type = r.type(key).decode()

    print(f"  Key: {decode_safe(key)}")
    print(f"  Type: {key_type}")

    if key_type == "string":
        value = r.get(key)
        print(f"  Value: {decode_safe(value)}")

    elif key_type == "hash":
        fields = r.hgetall(key)
        print("  Fields:")
        for f, v in fields.items():
            print(f"    {decode_safe(f)} = {decode_safe(v)}")

    elif key_type == "list":
        values = r.lrange(key, 0, -1)
        print("  Items:")
        for i, v in enumerate(values):
            print(f"    [{i}] {decode_safe(v)}")

    elif key_type == "set":
        members = r.smembers(key)
        print("  Members:")
        for m in members:
            print(f"    {decode_safe(m)}")

    elif key_type == "zset":
        members = r.zrange(key, 0, -1, withscores=True)
        print("  Sorted Set Members:")
        for m, score in members:
            print(f"    {decode_safe(m)} (score={score})")

    else:
        print("  [unknown type]")

    print()  # blank line between keys


def show_database(name, r):
    """Display all keys and values for a given Redis instance."""
    print(f"\n=== {name} Redis ===")

    try:
        keys = r.keys()
    except Exception as e:
        print(f"[error] Unable to query keys: {e}")
        return

    if not keys:
        print("  (no keys)")
        return

    for key in keys:
        print_key_value(r, key)


def main():
    local = redis_conn(LOCAL_REDIS_HOST, LOCAL_REDIS_PORT)
    # No remote in single node mode
    remote = redis_conn(REMOTE_REDIS_HOST, REMOTE_REDIS_PORT) if config["dual"] else None

    try:
        local.ping()
        if remote is not None:
            remote.ping()
    except Exception as e:
        print(f"[error] Cannot connect: {e}")
        sys.exit(1)

    show_database("LOCAL", local)
    if remote is not None:
        show_database("REMOTE", remote)


if __name__ == "__main__":
    main()

