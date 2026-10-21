"""
face.py

The decision logic of Factor 3 (facial recognition), with no camera, UI or face_recognition
import so it can be tested anywhere. The camera/recognition thread feeds it one observation per
recognition pass and the UI reads the state.

How it decides (unchanged from tk_open_vault.py):
  - The timer (timer_seconds) starts on the first pass that sees a face. If no face appears
    within face_wait_seconds the factor fails.
  - Each pass after that is a vote: a pass with no face, or whose closest face is further from
    the card holder's enrolled encoding than match_threshold, counts as a miss.
  - The factor passes as soon as vote_required of the last vote_window votes matched. The
    result is locked in, and the live video carries on for pass_hold_seconds so the person can
    see they have been recognised.
"""

import time
from collections import deque

WAITING = "waiting"      # no face seen yet
VERIFYING = "verifying"  # a face has been seen and the timer is running
PASSED = "passed"
FAILED = "failed"


def closest_face(distances):
    """Given each face's distance to the card holder, return (index, distance) of the closest,
    or (-1, None) if there are no faces. The closest face is taken to be the card holder and
    any others are bystanders."""
    if len(distances) == 0:
        return -1, None
    index = min(range(len(distances)), key=lambda i: distances[i])
    return index, float(distances[index])


class FaceVerifier:
    def __init__(self, match_threshold, vote_window, vote_required, timer_seconds,
                 face_wait_seconds, pass_hold_seconds, clock=time.monotonic):
        self.match_threshold = match_threshold
        self.vote_required = vote_required
        self.timer_seconds = timer_seconds
        self.face_wait_seconds = face_wait_seconds
        self.pass_hold_seconds = pass_hold_seconds
        self.votes = deque(maxlen=vote_window)
        self.state = WAITING
        self._clock = clock
        self._wait_start = clock()
        self._timer_start = None
        self._pass_time = None

    @classmethod
    def from_config(cls, config, clock=time.monotonic):
        return cls(config["match_threshold"], config["vote_window"], config["vote_required"],
                   config["timer_seconds"], config["face_wait_seconds"],
                   config["pass_hold_seconds"], clock)

    @property
    def matches(self):
        """How many of the votes in the window were matches."""
        return sum(self.votes)

    @property
    def finished(self):
        """True when the factor has failed, or has passed and the pass hold has elapsed."""
        if self.state == FAILED:
            return True
        return self.state == PASSED and self._clock() - self._pass_time >= self.pass_hold_seconds

    def is_match(self, distance):
        return distance is not None and distance <= self.match_threshold

    def tick(self):
        """Check the time limits. Call once per camera frame, before observe()."""
        now = self._clock()
        if self.state == WAITING and now - self._wait_start >= self.face_wait_seconds:
            self.state = FAILED
        elif self.state == VERIFYING and now - self._timer_start >= self.timer_seconds:
            self.state = FAILED
        return self.state

    def observe(self, face_count, best_distance):
        """Record one recognition pass and return whether it matched the card holder.

        face_count is the number of faces seen; best_distance is the closest face's distance
        to the card holder (None if there are no faces or nobody to match against).
        """
        matched = self.is_match(best_distance)
        if self.state in (PASSED, FAILED):
            return matched  # the result is locked, so a later bad frame can't undo it

        if self.state == WAITING and face_count > 0:
            self.state = VERIFYING
            self._timer_start = self._clock()
        if self.state == VERIFYING:
            self.votes.append(matched)
            if self.matches >= self.vote_required:
                self.state = PASSED
                self._pass_time = self._clock()
        return matched

    def seconds_left(self):
        """Time left on the clock that is currently running (the wait for a face, or the
        timer), for the UI to show. 0 once the factor has passed or failed."""
        now = self._clock()
        if self.state == WAITING:
            return max(0.0, self.face_wait_seconds - (now - self._wait_start))
        if self.state == VERIFYING:
            return max(0.0, self.timer_seconds - (now - self._timer_start))
        return 0.0
