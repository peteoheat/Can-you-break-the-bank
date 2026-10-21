"""
pin_game.py

The logic of Factor 2, the Wordle-style PIN game, with no user interface so the single-window
app can show it in frame 2 and the tests can run it anywhere.

Each guess is scored digit by digit:
  correct   = digit and position correct (green)
  misplaced = digit is in the PIN but in a different position (amber)
  wrong     = digit is not in the PIN (grey)

The game ends when the PIN is guessed (even on the last allowed guess), when max_guesses wrong
guesses have been made, or when time_limit_seconds has run out.
"""

import time

CORRECT = "correct"
MISPLACED = "misplaced"
WRONG = "wrong"

PLAYING = "playing"
PASSED = "passed"
OUT_OF_GUESSES = "out_of_guesses"
OUT_OF_TIME = "out_of_time"


def is_valid_pin(text, length):
    """True if text is exactly `length` ASCII digits. Also used to check PINs at enrolment."""
    return len(text) == length and text.isascii() and text.isdigit()


def compare(guess, secret):
    """Score a guess against the secret: a list of (status, digit), one per position."""
    feedback = []
    for position, digit in enumerate(guess):
        if digit == secret[position]:
            feedback.append((CORRECT, digit))
        elif digit in secret:
            feedback.append((MISPLACED, digit))
        else:
            feedback.append((WRONG, digit))
    return feedback


class PinGame:
    def __init__(self, secret, max_guesses, time_limit_seconds, clock=time.monotonic):
        self.secret = secret
        self.max_guesses = max_guesses
        self.time_limit_seconds = time_limit_seconds
        self.guesses = []  # (guess, feedback) in the order they were made
        self.outcome = PLAYING
        self._clock = clock
        self._deadline = None

    @property
    def length(self):
        return len(self.secret)

    @property
    def guesses_left(self):
        return self.max_guesses - len(self.guesses)

    def start(self):
        """Start the countdown."""
        self._deadline = self._clock() + self.time_limit_seconds

    def remaining_seconds(self):
        if self._deadline is None:
            return float(self.time_limit_seconds)
        return max(0.0, self._deadline - self._clock())

    def check_time(self):
        """Call regularly (e.g. from a UI timer). Ends the game once time has run out."""
        if self.outcome == PLAYING and self._deadline is not None and self.remaining_seconds() <= 0:
            self.outcome = OUT_OF_TIME
        return self.outcome

    def submit(self, guess):
        """Score a guess and return its feedback.

        Raises ValueError if the guess is not the right length or not all digits (it doesn't
        count as an attempt), and RuntimeError if the game is already over.
        """
        if self.check_time() != PLAYING:
            raise RuntimeError(f"The game is over ({self.outcome})")
        if not is_valid_pin(guess, self.length):
            raise ValueError(f"Please enter a valid {self.length}-digit number.")

        feedback = compare(guess, self.secret)
        self.guesses.append((guess, feedback))
        if guess == self.secret:
            self.outcome = PASSED
        elif self.guesses_left <= 0:
            self.outcome = OUT_OF_GUESSES
        return feedback
