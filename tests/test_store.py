import pickle
import unittest

from store import Card, CardStore


class FakeRedis:
    """Just enough of redis.StrictRedis (decode_responses=False) for CardStore."""

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


class CardStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = CardStore(FakeRedis())

    def test_round_trip(self):
        self.store.save(Card("0123456789AB", "Ada", "1234", [0.1, 0.2]))
        card = self.store.get("0123456789AB")
        self.assertEqual((card.card_id, card.name, card.pin, card.encoding), ("0123456789AB", "Ada", "1234", [0.1, 0.2]))

    def test_get_unknown_card(self):
        self.assertIsNone(self.store.get("nope"))
        self.assertFalse(self.store.exists("nope"))

    def test_save_replaces_existing(self):
        self.store.save(Card("A", "Ada", "1111", [1]))
        self.store.save(Card("A", "Ada L", "2222", [2]))
        self.assertEqual(self.store.get("A").pin, "2222")
        self.assertEqual(len(self.store.load_cards()), 1)

    def test_load_cards(self):
        self.store.save(Card("A", "Ada", "1111", [1]))
        self.store.save(Card("B", "Bob", "2222", [2]))
        self.assertEqual(sorted(c.name for c in self.store.load_cards()), ["Ada", "Bob"])

    def test_reads_the_layout_the_old_scripts_wrote(self):
        self.store.client.data["card:X"] = {"name": b"Old", "pin": b"9999", "encoding": pickle.dumps([3])}
        self.assertEqual(self.store.get("X").encoding, [3])


if __name__ == "__main__":
    unittest.main()
