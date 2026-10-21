"""
store.py

Reads and writes enrolled users in Redis, shared by the vault and enrolment parts of the app.
Each user is a hash at card:<id> with name, pin and a pickled face encoding (the same layout
tk_add_user.py wrote and tk_open_vault.py read), so existing enrolments keep working and
redis-sync.py replicates them as before.

Redis stays the local one: in dual node mode redis-sync.py copies the changes to the other Pi.
"""

import pickle
from dataclasses import dataclass

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
