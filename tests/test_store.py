import pickle
import unittest

from store import Card, CardStore, MemoryRedis, create_store


class CardStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = CardStore(MemoryRedis())

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


class CreateStoreTests(unittest.TestCase):
    # Port 1 has nothing listening, so Redis is unreachable (or the redis package is missing)
    config = {"local_host": "127.0.0.1", "local_port": 1}

    def test_falls_back_to_memory_unless_hardware_is_real(self):
        store, in_memory = create_store(dict(self.config, hardware_backend="simulated"))
        self.assertTrue(in_memory)
        self.assertEqual(store.load_cards(), [])

    def test_real_hardware_needs_redis(self):
        with self.assertRaises(Exception):
            create_store(dict(self.config, hardware_backend="real"), wait_seconds=0)


if __name__ == "__main__":
    unittest.main()
