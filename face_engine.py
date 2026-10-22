"""
face_engine.py

Finds faces and works out how far apart two faces are. RealFaceEngine uses the face_recognition
library (as the old scripts did); SimulatedFaceEngine pretends there is always one face in the
middle of the frame, so the app can be developed on a machine without dlib.

create_face_engine(config) picks one from [hardware] backend: real, simulated, or auto (real if
face_recognition imports, otherwise simulated with a warning).

Importing this module doesn't import face_recognition.
"""

import logging
import math
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("face_engine")


@dataclass
class Face:
    box: tuple  # (top, right, bottom, left) in the pixels of the frame given to detect()
    encoding: object  # numpy array of 128 floats
    landmarks: object = None  # {feature name: [(x, y), ...]} when detect() was asked for them


class RealFaceEngine:
    simulated = False

    def __init__(self):
        import face_recognition
        self._fr = face_recognition

    def detect(self, rgb_frame, landmarks=False):
        """Return the Faces in an RGB frame, with their facial features (chin, eyes, nose, lips and
        so on) if landmarks is true."""
        boxes = self._fr.face_locations(rgb_frame, model="hog")
        encodings = self._fr.face_encodings(rgb_frame, boxes)
        features = self._fr.face_landmarks(rgb_frame, face_locations=boxes) if landmarks else [None] * len(boxes)
        return [Face(box, encoding, feature) for box, encoding, feature in zip(boxes, encodings, features)]

    def distances(self, encodings, target):
        """The distance from each of the encodings to the target encoding."""
        if len(encodings) == 0:
            return []
        return [float(d) for d in self._fr.face_distance(encodings, target)]


def simulated_landmarks(box):
    """Plausible facial features inside a (top, right, bottom, left) box, named as face_recognition
    names them, for the simulated engine."""
    top, right, bottom, left = box
    width, height = right - left, bottom - top

    def at(x, y):  # a point given as a fraction of the box
        return (int(left + x * width), int(top + y * height))

    def line(x0, y0, x1, y1, n):
        return [at(x0 + (x1 - x0) * i / (n - 1), y0 + (y1 - y0) * i / (n - 1)) for i in range(n)]

    chin = [at(0.5 - 0.5 * math.cos(t), 0.35 + 0.65 * math.sin(t)) for t in np.linspace(0, math.pi, 17)]
    return {
        "chin": chin,
        "left_eyebrow": line(0.15, 0.30, 0.40, 0.27, 5),
        "right_eyebrow": line(0.60, 0.27, 0.85, 0.30, 5),
        "nose_bridge": line(0.50, 0.35, 0.50, 0.55, 4),
        "nose_tip": line(0.38, 0.62, 0.62, 0.62, 5),
        "left_eye": [at(0.20, 0.40), at(0.27, 0.37), at(0.35, 0.37), at(0.40, 0.40), at(0.35, 0.43), at(0.27, 0.43)],
        "right_eye": [at(0.60, 0.40), at(0.65, 0.37), at(0.73, 0.37), at(0.80, 0.40), at(0.73, 0.43), at(0.65, 0.43)],
        "top_lip": line(0.33, 0.78, 0.67, 0.78, 12),
        "bottom_lip": line(0.67, 0.80, 0.33, 0.80, 12),
    }


class SimulatedFaceEngine:
    simulated = True
    # Every simulated face is this encoding plus a little noise, so anyone enrolled with the
    # simulated engine matches (distance well under the 0.55 threshold)
    BASE = np.linspace(-0.1, 0.1, 128)

    def __init__(self):
        self._random = np.random.default_rng()

    def detect(self, rgb_frame, landmarks=False):
        height, width = rgb_frame.shape[:2]
        box = (height // 4, width * 3 // 4, height * 3 // 4, width // 4)
        features = simulated_landmarks(box) if landmarks else None
        return [Face(box, self.BASE + self._random.normal(0, 0.003, 128), features)]

    def distances(self, encodings, target):
        if len(encodings) == 0:
            return []
        return [float(d) for d in np.linalg.norm(np.asarray(encodings) - np.asarray(target), axis=1)]


def create_face_engine(config):
    backend = config["hardware_backend"]
    if backend == "simulated":
        return SimulatedFaceEngine()
    if backend == "real":
        return RealFaceEngine()
    try:  # auto
        return RealFaceEngine()
    except ImportError as error:
        log.warning("face_recognition not available (%s) - using the simulated face engine", error)
        return SimulatedFaceEngine()
