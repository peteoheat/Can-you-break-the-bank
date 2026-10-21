"""
store.py

Reads and writes enrolled users in Redis, shared by the vault and enrolment parts of the app.
Each user is a hash at card:<id> with name, pin and a pickled face encoding (the same layout
tk_add_user.py wrote and tk_open_vault.py read), so existing enrolments keep working and
redis-sync.py replicates them as before.

Redis stays the local one: in dual node mode redis-sync.py copies the changes to the other Pi.
"""

import logging
import pickle
from dataclasses import dataclass

log = logging.getLogger("store")

KEY_PREFIX = "card:"


@dataclass
class Card:
    card_id: str
    name: str
    pin: str
    encoding: object  # numpy array of 128 floats


def connect(config):
    """Open the local Redis from the config (imported here so tests don't need redis)."""
    import redis
    return redis.StrictRedis(host=config["local_host"], port=config["local_port"], decode_responses=False)


class MemoryRedis:
    """Just enough of redis.StrictRedis (decode_responses=False) for CardStore, held in memory.
    Used by the tests, and when developing without a Redis server."""

    def __init__(self):
        self.data = {}

    def scan_iter(self, pattern):
        prefix = pattern.rstrip("*")
        return [k.encode() for k in list(self.data) if k.startswith(prefix)]

    def hgetall(self, key):
        return {k.encode(): v if isinstance(v, bytes) else str(v).encode() for k, v in self.data.get(key, {}).items()}

    def hset(self, key, mapping):
        self.data.setdefault(key, {}).update(mapping)

    def delete(self, key):
        self.data.pop(key, None)

    def exists(self, key):
        return int(key in self.data)


def create_store(config):
    """Return a CardStore on the local Redis. If Redis isn't reachable and the hardware is not
    forced to real, use an in-memory store instead (so the app runs on a development machine).
    Returns (store, in_memory)."""
    try:
        client = connect(config)
        client.ping()
        return CardStore(client), False
    except Exception as error:
        if config["hardware_backend"] == "real":
            raise
        log.warning("Redis not available (%s) - using an in-memory store, enrolments will not be kept", error)
        return CardStore(MemoryRedis()), True


class CardStore:
    def __init__(self, client):
        self.client = client

    def load_cards(self):
        """Return every enrolled user as a list of Card."""
        cards = []
        for key in self.client.scan_iter(f"{KEY_PREFIX}*"):
            card_id = key.decode("utf-8").split(":", 1)[1]
            card = self.get(card_id)
            if card is not None:
                cards.append(card)
        return cards

    def get(self, card_id):
        """Return the Card for card_id, or None if it isn't enrolled."""
        data = self.client.hgetall(f"{KEY_PREFIX}{card_id}")
        if not data:
            return None
        return Card(card_id, data[b"name"].decode("utf-8"), data[b"pin"].decode("utf-8"),
                    pickle.loads(data[b"encoding"]))

    def exists(self, card_id):
        return bool(self.client.exists(f"{KEY_PREFIX}{card_id}"))

    def save(self, card):
        """Enrol a user, replacing any existing entry for the same card."""
        key = f"{KEY_PREFIX}{card.card_id}"
        self.client.delete(key)
        self.client.hset(key, mapping={
            "name": card.name,
            "pin": card.pin,
            "encoding": pickle.dumps(card.encoding),
        })
