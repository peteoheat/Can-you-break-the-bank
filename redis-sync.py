#!/usr/bin/env python3
import redis
import time
import os
import logging

# -----------------------------
# Configuration
# -----------------------------
LOCAL_REDIS_HOST = os.environ.get("LOCAL_REDIS_HOST", "127.0.0.1")
LOCAL_REDIS_PORT = int(os.environ.get("LOCAL_REDIS_PORT", "6379"))

REMOTE_REDIS_HOST = os.environ.get("REMOTE_REDIS_HOST", "192.168.8.153")  # set to the other Pi's IP
REMOTE_REDIS_PORT = int(os.environ.get("REMOTE_REDIS_PORT", "6379"))

RETRY_INTERVAL = 60  # seconds

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
log = logging.getLogger("redis-sync")

# -----------------------------
# Redis connections
# -----------------------------
def redis_conn(host, port):
    return redis.Redis(host=host, port=port, decode_responses=False)

local = redis_conn(LOCAL_REDIS_HOST, LOCAL_REDIS_PORT)
remote = redis_conn(REMOTE_REDIS_HOST, REMOTE_REDIS_PORT)

# Enable keyspace notifications
local.config_set("notify-keyspace-events", "AKE")

# -----------------------------
# Key copy / sync functions
# -----------------------------
def copy_key(src, dst, key):
    try:
        key_type = src.type(key).decode()
        ttl = src.ttl(key)

        # Use a marker to avoid triggering loops
        marker = b"__sync_applying__:" + key if isinstance(key, bytes) else b"__sync_applying__:" + key.encode()
        dst.set(marker, b"1")

        if key_type == "string":
            value = src.get(key)
            if ttl > 0:
                dst.setex(key, ttl, value)
            else:
                dst.set(key, value)

        elif key_type == "hash":
            hash_data = src.hgetall(key)
            dst.hset(key, mapping=hash_data)
            if ttl > 0:
                dst.expire(key, ttl)

        elif key_type == "list":
            dst.delete(key)
            for item in src.lrange(key, 0, -1):
                dst.rpush(key, item)
            if ttl > 0:
                dst.expire(key, ttl)

        elif key_type == "set":
            dst.delete(key)
            dst.sadd(key, *src.smembers(key))
            if ttl > 0:
                dst.expire(key, ttl)

        elif key_type == "zset":
            dst.delete(key)
            for member, score in src.zrange(key, 0, -1, withscores=True):
                dst.zadd(key, {member: score})
            if ttl > 0:
                dst.expire(key, ttl)

        dst.delete(marker)
        log.info(f"Copied key '{key.decode() if isinstance(key, bytes) else key}'")
    except Exception as e:
        log.error(f"Error copying key '{key}': {e}")

def initial_two_way_sync():
    log.info("Starting initial two-way sync")
    try:
        local_keys = set(local.keys("*"))
        remote_keys = set(remote.keys("*"))

        # Copy keys missing locally
        for key in remote_keys - local_keys:
            copy_key(remote, local, key)

        # Copy keys missing remotely
        for key in local_keys - remote_keys:
            copy_key(local, remote, key)

        # Keys in both sides — leave unchanged to avoid conflict
        for key in local_keys & remote_keys:
            log.warning(f"Key '{key.decode() if isinstance(key, bytes) else key}' exists on both sides — skipping")

        log.info("Initial sync complete")
    except Exception as e:
        log.error(f"Initial sync failed: {e}")
        time.sleep(RETRY_INTERVAL)
        initial_two_way_sync()

# -----------------------------
# Keyspace event listener
# -----------------------------
def replicate_change(message):
    if message["type"] != "pmessage":
        return
    key = message["channel"].split(b":", 1)[1]
    event = message["data"]

    if key.startswith(b"__sync_applying__"):
        return  # skip our own markers

    key_type = local.type(key).decode()
    try:
        if event == b"set" and key_type == "string":
            remote.set(key, local.get(key))
        elif event == b"hset" and key_type == "hash":
            remote.hset(key, mapping=local.hgetall(key))
        elif event == b"del":
            remote.delete(key)
        elif event == b"expire":
            ttl = local.ttl(key)
            if key_type == "string":
                remote.setex(key, ttl, local.get(key))
            elif key_type == "hash":
                remote.hset(key, mapping=local.hgetall(key))
                remote.expire(key, ttl)
    except Exception as e:
        log.error(f"Error replicating key '{key.decode() if isinstance(key, bytes) else key}': {e}")

def listen_for_changes():
    pubsub = local.pubsub()
    pubsub.psubscribe("__keyspace@0__:*")
    log.info("Listening for local keyspace events...")
    for message in pubsub.listen():
        replicate_change(message)

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    initial_two_way_sync()
    listen_for_changes()

