"""
camera_worker.py

The camera and face recognition run on their own threads so the UI never waits for them (the old
vault app ran both in a loop on the UI thread).

  CameraWorker       captures frames continuously, draws the latest overlay (face boxes and a
                     banner) on them and emits them as QImages for the camera pane.
  RecognitionWorker  takes the most recent frame it is offered, finds faces and works out who
                     they are, and emits a Result. Frames offered while it is busy are dropped.

The recognition mode says what to do with each frame: OFF, VERIFY (Factor 3: compare with the
scanned card's enrolled face) or ENROL (collect the face encodings and find the facial features
to draw on the live view). Each result carries the
session number it was made for, so the app can ignore results left over from an earlier session.

Frames are BGR, as both camera types give them (see camera_setup.py); they are converted to RGB
before recognition, as in enrolment.
"""

import logging
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from face import closest_face

log = logging.getLogger("camera")

OFF = "off"
VERIFY = "verify"
ENROL = "enrol"

# Box colours, in BGR
RED = (0, 0, 255)
GREEN = (0, 255, 0)
AMBER = (0, 125, 255)
WHITE = (255, 255, 255)


@dataclass
class FaceView:
    box: tuple  # (top, right, bottom, left) in full-frame pixels
    name: str
    card: str
    colour: tuple


@dataclass
class Result:
    session: int
    mode: str
    faces: list  # FaceView
    face_count: int
    best_distance: object = None  # closest face to the card holder (VERIFY), else None
    is_match: bool = False
    face_mean: object = None  # brightness of the card holder's face, to spot lighting problems
    face_std: object = None
    encodings: list = field(default_factory=list)  # ENROL: one per face, in the same order as faces
    landmarks: list = field(default_factory=list)  # ENROL: {feature: [(x, y), ...]} per face, in full-frame pixels


@dataclass
class Overlay:
    faces: list = field(default_factory=list)
    banner: str = ""
    banner_colour: tuple = GREEN
    landmarks: list = field(default_factory=list)  # {feature: [(x, y), ...]} per face, drawn as red lines


class SyntheticCamera:
    """Stands in for the camera on a development machine with no camera."""

    def __init__(self, width, height, frame_rate):
        self.width, self.height, self.delay = width, height, 1 / frame_rate
        self.start = time.monotonic()

    def capture_array(self):
        time.sleep(self.delay)
        elapsed = time.monotonic() - self.start
        frame = np.full((self.height, self.width, 3), (60, 45, 35), np.uint8)
        x = int(elapsed * 80) % self.width
        cv2.circle(frame, (x, self.height // 2), self.height // 8, (90, 160, 200), -1)
        cv2.putText(frame, "SIMULATED CAMERA", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, WHITE, 2)
        return frame

    def close(self):
        pass


def open_app_camera(config):
    """Open the configured camera. Unless [hardware] backend is real, a camera that can't be opened
    is replaced by a synthetic one so the app can still run. Returns (camera, is_synthetic)."""
    from camera_setup import open_camera
    try:
        return open_camera(config), False
    except Exception as error:
        if config["hardware_backend"] == "real":
            raise
        log.warning("Camera not available (%s) - using a synthetic camera", error)
        return SyntheticCamera(config["frame_width"], config["frame_height"], config["frame_rate"]), True


def to_qimage(bgr_frame):
    rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    return QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()


class CameraWorker(QThread):
    frame_ready = pyqtSignal(QImage)
    failed = pyqtSignal(str)

    def __init__(self, camera, recogniser, recognise_every_n):
        super().__init__()
        self.camera = camera
        self.recogniser = recogniser
        self.recognise_every_n = recognise_every_n
        self.overlay = Overlay()  # replaced whole by the UI thread, so no lock is needed
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        self.wait()

    def run(self):
        frame_number = 0
        try:
            while not self._stop.is_set():
                frame = self.camera.capture_array()
                if frame_number % self.recognise_every_n == 0:
                    self.recogniser.offer(frame)
                frame_number += 1
                self._draw(frame, self.overlay)
                self.frame_ready.emit(to_qimage(frame))
        except Exception as error:
            log.exception("Camera failed")
            self.failed.emit(str(error))

    @staticmethod
    def _draw(frame, overlay):
        thickness = max(2, round(frame.shape[0] / 160))  # 3 on a 640x480 frame, as in the old enrolment
        for face_features in overlay.landmarks:
            for points in face_features.values():
                cv2.polylines(frame, [np.array(points, np.int32)], False, RED, thickness)
        for face in overlay.faces:
            top, right, bottom, left = face.box
            cv2.rectangle(frame, (left, top), (right, bottom), face.colour, 2)
            name_y = top - 15 if top - 15 > 15 else top + 15
            cv2.putText(frame, face.name, (left, name_y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, face.colour, 2)
            cv2.putText(frame, face.card, (left, bottom + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, face.colour, 2)
        if overlay.banner:
            cv2.rectangle(frame, (0, 0), (frame.shape[1], 50), overlay.banner_colour, -1)
            cv2.putText(frame, overlay.banner, (15, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, WHITE, 2)


class RecognitionWorker(QThread):
    result_ready = pyqtSignal(object)

    def __init__(self, engine, match_threshold, small_frame_scale):
        super().__init__()
        self.engine = engine
        self.match_threshold = match_threshold
        self.small_frame_scale = small_frame_scale
        self.box_scale = round(1 / small_frame_scale)  # 1/small_frame_scale must be a whole number
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._frame = None
        self._mode = OFF
        self._session = 0
        self._claimed = None  # the Card being verified
        self._known = []

    def configure(self, mode, session, claimed=None, known=()):
        """Set what to do with frames. claimed is the scanned card's Card and known is every
        enrolled Card (VERIFY), so bystanders can be boxed amber if they're enrolled."""
        with self._lock:
            self._mode, self._session, self._claimed, self._known = mode, session, claimed, list(known)
            self._frame = None

    def offer(self, frame):
        """Give the worker a frame to look at, unless it is off or still busy with the last."""
        with self._lock:
            if self._mode == OFF or self._frame is not None:
                return
            self._frame = frame.copy()  # the camera thread draws on the original
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()
        self.wait()

    def run(self):
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                frame, mode, session = self._frame, self._mode, self._session
                claimed, known = self._claimed, self._known
            if frame is None or self._stop.is_set():
                continue
            try:
                result = self._process(frame, mode, session, claimed, known)
            except Exception:
                log.exception("Recognition failed")
                result = None
            with self._lock:
                self._frame = None
            if result is not None:
                self.result_ready.emit(result)

    def _process(self, frame, mode, session, claimed, known):
        scale = self.small_frame_scale
        small = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
        faces = self.engine.detect(cv2.cvtColor(small, cv2.COLOR_BGR2RGB), landmarks=(mode == ENROL))
        views, best_distance, is_match, face_mean, face_std = [], None, False, None, None
        encodings, landmarks = [], []

        def scaled(box):
            return tuple(v * self.box_scale for v in box)

        if mode == ENROL:
            views = [FaceView(scaled(f.box), "Capturing", "", GREEN) for f in faces]
            encodings = [f.encoding for f in faces]
            landmarks = [{feature: [(x * self.box_scale, y * self.box_scale) for x, y in points]
                          for feature, points in f.landmarks.items()} for f in faces if f.landmarks]
        elif mode == VERIFY and claimed is not None:
            distances = self.engine.distances([f.encoding for f in faces], claimed.encoding)
            # The closest face is taken to be the card holder; the rest are bystanders and ignored
            best_index, best_distance = closest_face(distances)
            is_match = best_distance is not None and best_distance <= self.match_threshold
            for i, face in enumerate(faces):
                name, card, colour = "Unauthorised", "No card", RED
                if i == best_index and is_match:
                    name, card, colour = claimed.name, claimed.card_id, GREEN
                elif known:
                    other = self.engine.distances([k.encoding for k in known], face.encoding)
                    k, distance = closest_face(other)
                    if distance <= self.match_threshold and known[k].card_id != claimed.card_id:
                        name, card, colour = known[k].name, known[k].card_id, AMBER
                views.append(FaceView(scaled(face.box), name, card, colour))
            if best_index >= 0:
                top, right, bottom, left = faces[best_index].box
                crop = cv2.cvtColor(small[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
                if crop.size > 0:
                    face_mean, face_std = round(float(crop.mean()), 1), round(float(crop.std()), 1)
        return Result(session, mode, views, len(faces), best_distance, is_match, face_mean, face_std, encodings, landmarks)
