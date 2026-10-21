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
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("face_engine")


@dataclass
class Face:
    box: tuple  # (top, right, bottom, left) in the pixels of the frame given to detect()
    encoding: object  # numpy array of 128 floats


class RealFaceEngine:
    simulated = False

    def __init__(self):
        import face_recognition
        self._fr = face_recognition

    def detect(self, rgb_frame):
        """Return the Faces in an RGB frame."""
        boxes = self._fr.face_locations(rgb_frame, model="hog")
        encodings = self._fr.face_encodings(rgb_frame, boxes)
        return [Face(box, encoding) for box, encoding in zip(boxes, encodings)]

    def distances(self, encodings, target):
        """The distance from each of the encodings to the target encoding."""
        if len(encodings) == 0:
            return []
        return [float(d) for d in self._fr.face_distance(encodings, target)]


class SimulatedFaceEngine:
    simulated = True
    # Every simulated face is this encoding plus a little noise, so anyone enrolled with the
    # simulated engine matches (distance well under the 0.55 threshold)
    BASE = np.linspace(-0.1, 0.1, 128)

    def __init__(self):
        self._random = np.random.default_rng()

    def detect(self, rgb_frame):
        height, width = rgb_frame.shape[:2]
        box = (height // 4, width * 3 // 4, height * 3 // 4, width // 4)
        return [Face(box, self.BASE + self._random.normal(0, 0.003, 128))]

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
