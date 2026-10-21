import unittest

from face import FaceVerifier, closest_face, WAITING, VERIFYING, PASSED, FAILED


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ClosestFaceTests(unittest.TestCase):
    def test_none(self):
        self.assertEqual(closest_face([]), (-1, None))

    def test_picks_smallest(self):
        self.assertEqual(closest_face([0.7, 0.4, 0.6]), (1, 0.4))


class FaceVerifierTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        # vote 3 of the last 5, 10s timer, 30s to find a face, 3s pass hold
        self.verifier = FaceVerifier(0.55, 5, 3, 10, 30, 3, self.clock)

    def test_starts_waiting(self):
        self.assertEqual(self.verifier.state, WAITING)
        self.assertEqual(self.verifier.seconds_left(), 30)

    def test_passes_after_enough_matches(self):
        for _ in range(3):
            self.verifier.observe(1, 0.4)
        self.assertEqual(self.verifier.state, PASSED)

    def test_threshold_is_inclusive(self):
        self.assertTrue(self.verifier.is_match(0.55))
        self.assertFalse(self.verifier.is_match(0.56))
        self.assertFalse(self.verifier.is_match(None))

    def test_first_face_starts_timer_and_counts_as_a_vote(self):
        self.clock.now = 5
        self.verifier.observe(1, 0.4)
        self.assertEqual(self.verifier.state, VERIFYING)
        self.assertEqual(self.verifier.matches, 1)
        self.clock.now = 8
        self.assertEqual(self.verifier.seconds_left(), 7)

    def test_no_face_casts_no_votes_before_the_timer_starts(self):
        self.verifier.observe(0, None)
        self.assertEqual(self.verifier.state, WAITING)
        self.assertEqual(len(self.verifier.votes), 0)

    def test_misses_are_votes_once_the_timer_started(self):
        self.verifier.observe(1, 0.9)
        self.verifier.observe(0, None)
        self.assertEqual(list(self.verifier.votes), [False, False])

    def test_only_the_last_window_counts(self):
        # Two matches, then five misses push them out of the five vote window,
        # so two more matches are not enough
        for distance in (0.4, 0.4, 0.9, 0.9, 0.9, 0.9, 0.9, 0.4, 0.4):
            self.verifier.observe(1, distance)
        self.assertEqual(self.verifier.state, VERIFYING)

    def test_fails_if_no_face_appears(self):
        self.clock.now = 29
        self.assertEqual(self.verifier.tick(), WAITING)
        self.clock.now = 30
        self.assertEqual(self.verifier.tick(), FAILED)
        self.assertTrue(self.verifier.finished)

    def test_fails_when_timer_runs_out(self):
        self.verifier.observe(1, 0.9)
        self.clock.now = 10
        self.assertEqual(self.verifier.tick(), FAILED)

    def test_result_is_locked_once_passed(self):
        for _ in range(3):
            self.verifier.observe(1, 0.4)
        for _ in range(10):
            self.verifier.observe(1, 0.9)
        self.assertEqual(self.verifier.state, PASSED)
        self.clock.now = 100  # even a timeout later can't undo it
        self.assertEqual(self.verifier.tick(), PASSED)

    def test_finished_after_pass_hold(self):
        for _ in range(3):
            self.verifier.observe(1, 0.4)
        self.assertFalse(self.verifier.finished)
        self.clock.now = 3
        self.assertTrue(self.verifier.finished)

    def test_from_config(self):
        config = {"match_threshold": 0.5, "vote_window": 8, "vote_required": 5, "timer_seconds": 10,
                  "face_wait_seconds": 30, "pass_hold_seconds": 3}
        verifier = FaceVerifier.from_config(config, self.clock)
        self.assertEqual(verifier.vote_required, 5)
        self.assertEqual(verifier.votes.maxlen, 8)


if __name__ == "__main__":
    unittest.main()
