import unittest

from pin_game import (CORRECT, MISPLACED, WRONG, PLAYING, PASSED, OUT_OF_GUESSES, OUT_OF_TIME,
                      PinGame, compare, is_valid_pin)


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class IsValidPinTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(is_valid_pin("1234", 4))

    def test_wrong_length_or_not_digits(self):
        for text in ("123", "12345", "12a4", "", "12 4", "²²²²"):
            self.assertFalse(is_valid_pin(text, 4), text)


class CompareTests(unittest.TestCase):
    def test_all_correct(self):
        self.assertEqual([s for s, _ in compare("1234", "1234")], [CORRECT] * 4)

    def test_misplaced_and_wrong(self):
        self.assertEqual(compare("4156", "1234"),
                         [(MISPLACED, "4"), (MISPLACED, "1"), (WRONG, "5"), (WRONG, "6")])


class PinGameTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.game = PinGame("1234", max_guesses=3, time_limit_seconds=45, clock=self.clock)
        self.game.start()

    def test_correct_guess_passes(self):
        self.game.submit("1234")
        self.assertEqual(self.game.outcome, PASSED)

    def test_out_of_guesses(self):
        for guess in ("0000", "1111", "2222"):
            self.assertEqual(self.game.outcome, PLAYING)
            self.game.submit(guess)
        self.assertEqual(self.game.outcome, OUT_OF_GUESSES)

    def test_correct_on_last_guess_passes(self):
        self.game.submit("0000")
        self.game.submit("1111")
        self.game.submit("1234")
        self.assertEqual(self.game.outcome, PASSED)

    def test_invalid_guess_is_not_an_attempt(self):
        with self.assertRaises(ValueError):
            self.game.submit("12")
        self.assertEqual(self.game.guesses_left, 3)

    def test_out_of_time(self):
        self.clock.now += 45
        self.assertEqual(self.game.check_time(), OUT_OF_TIME)
        with self.assertRaises(RuntimeError):
            self.game.submit("1234")

    def test_remaining_seconds(self):
        self.clock.now += 10
        self.assertEqual(self.game.remaining_seconds(), 35)

    def test_clock_does_not_run_before_start(self):
        game = PinGame("1234", 3, 45, clock=self.clock)
        self.clock.now += 1000
        self.assertEqual(game.check_time(), PLAYING)
        self.assertEqual(game.remaining_seconds(), 45)

    def test_no_submit_after_pass(self):
        self.game.submit("1234")
        with self.assertRaises(RuntimeError):
            self.game.submit("0000")


if __name__ == "__main__":
    unittest.main()
