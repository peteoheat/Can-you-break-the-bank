import unittest

from rfid import SimulatedCardReader


class SimulatedCardReaderTests(unittest.TestCase):
    def setUp(self):
        self.cards = []
        self.beeps = 0
        self.reader = SimulatedCardReader(self.cards.append, self.beep)

    def beep(self):
        self.beeps += 1

    def test_ignored_until_armed(self):
        self.reader.inject("A")
        self.assertEqual(self.cards, [])

    def test_delivers_once_then_disarms(self):
        self.reader.arm()
        self.reader.inject("A")
        self.reader.inject("B")
        self.assertEqual(self.cards, ["A"])
        self.assertEqual(self.beeps, 1)

    def test_rearm(self):
        self.reader.arm()
        self.reader.inject("A")
        self.reader.arm()
        self.reader.inject("B")
        self.assertEqual(self.cards, ["A", "B"])

    def test_disarm(self):
        self.reader.arm()
        self.reader.disarm()
        self.reader.inject("A")
        self.assertEqual(self.cards, [])


if __name__ == "__main__":
    unittest.main()
