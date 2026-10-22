#!/usr/bin/python3
"""
vault_app.py

Can you break the bank? - the whole activity in one window.

  Frame 1 (left, 70%)         the vault, access granted / denied and their videos
  Frame 2 (top right)         progress, instructions and the PIN game (or the enrolment form)
  Frame 3 (bottom right)      the live camera and face recognition feedback

Vault mode runs the three factors: card (RFID), PIN (Wordle-style game) and face. Enrol mode
adds users: scan a card, enter a name and PIN, then the face is captured. The mode can be switched
on screen (and starts as [app] mode in the config, or --mode).

Run with:  .venv/bin/python vault_app.py   (add --windowed to run in a window)
"""

import argparse
import csv
import logging
import sys
import time

import numpy as np
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QInputDialog, QLineEdit,
                             QPushButton, QVBoxLayout, QWidget)

import camera_worker
import face
import hardware as hw
import panes
import pin_game
from app_config import load_config
from camera_worker import CameraWorker, Overlay, RecognitionWorker, open_app_camera
from face_engine import create_face_engine
from rfid import SimulatedCardReader, create_card_reader
from store import Card, create_store

log = logging.getLogger("vault_app")

# What the app is doing
IDLE, PIN, FACE, RESULT = "idle", "pin", "face", "result"
ENROL_IDLE, ENROL_FORM, ENROL_CAPTURE = "enrol_idle", "enrol_form", "enrol_capture"
SWITCHABLE = (IDLE, ENROL_IDLE, ENROL_FORM)  # where it is safe to change mode or exit

VAULT_STEPS = ["1  CARD", "2  PIN", "3  FACE"]
ENROL_STEPS = ["1  CARD", "2  DETAILS", "3  FACE"]

STYLE = """
QWidget {{ background: transparent; color: #e8edf2; font-family: Quicksand, "DejaVu Sans", sans-serif; font-size: {body}px; }}
QWidget#root {{ background: #12161c; }}
QFrame#info, QFrame#camera {{ background: #1b222a; border-radius: {radius}px; }}
QAbstractItemView {{ background: #1b222a; }}
QTableWidget#features {{ font-size: {tiny}px; gridline-color: #2b3540; border: none; }}
QTableWidget#features QHeaderView::section {{ background: #2b3540; color: #c5d0da; padding: {pad_s}px; border: none; font-size: {tiny}px; }}
QLabel#title {{ font-size: {small}px; font-weight: bold; color: #9fb0c0; }}
QLabel#instruction {{ font-size: {big}px; font-weight: bold; }}
QLabel#detail, QLabel#caption {{ font-size: {body}px; color: #c5d0da; }}
QLabel#timer {{ font-size: {big}px; font-weight: bold; color: #ff5555; }}
QLabel#error {{ font-size: {body}px; color: #ff7070; }}
QLabel#legend {{ font-size: {small}px; padding: {pad}px; border-radius: {radius}px; }}
QLabel#chip {{ font-size: {small}px; font-weight: bold; padding: {pad}px; border-radius: {radius}px; background: #2b3540; color: #8fa0b0; }}
QLabel#chip[state="active"] {{ background: {amber}; color: black; }}
QLabel#chip[state="done"] {{ background: {green}; color: black; }}
QLabel#chip[state="failed"] {{ background: {red}; color: white; }}
QLineEdit {{ background: white; color: black; border-radius: {radius}px; padding: {pad_s}px {pad}px; font-size: {big}px; }}
QComboBox {{ background: white; color: black; padding: {pad_s}px; font-size: {body}px; }}
QPushButton {{ background: #2b3540; color: white; border-radius: {radius}px; padding: {pad}px {pad2}px; font-size: {body}px; }}
QPushButton#go {{ background: {green}; color: black; font-weight: bold; }}
QPushButton#small {{ font-size: {small}px; padding: {pad_s}px {pad}px; }}
QPushButton:disabled {{ background: #1f262e; color: #5c6a78; }}
"""


class MainWindow(QWidget):
    card_scanned = pyqtSignal(str)  # emitted from the card reader's thread

    def __init__(self, config, hardware, store, engine, camera, synthetic_camera):
        super().__init__()
        self.config, self.hardware, self.store, self.engine = config, hardware, store, engine
        self.setObjectName("root")
        self.setWindowTitle("Can you break the bank?")
        self.mode = config["app_mode"]
        self.state = None
        self.session = 0
        self.cards = []
        self.card = None
        self.game = None
        self.verifier = None
        self.log_file = self.log_writer = None
        self.enrol = {}
        self._after_video = None

        self.stage = panes.StagePane()
        self.info = panes.InfoPane(config["pin_length"])
        self.camera_pane = panes.CameraPane()
        self.stage.video_finished.connect(self._video_finished)
        self.info.mode_requested.connect(self.switch_mode)
        self.info.exit_requested.connect(self.exit_app)
        self.info.pin_game.guess_submitted.connect(self.on_guess)
        self.info.enrol_form.submitted.connect(self.on_enrol_submitted)
        self.info.enrol_form.cancelled.connect(self.reset_idle)

        self.right = right = QVBoxLayout()
        right.setSpacing(0)
        right.addWidget(self.info, 62)
        right.addWidget(self.camera_pane, 38)
        row = QHBoxLayout()
        row.setSpacing(0)
        row.addWidget(self.stage, 70)
        row.addLayout(right, 30)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(row, 1)

        # Camera and recognition threads
        self.recogniser = RecognitionWorker(engine, config["match_threshold"], config["small_frame_scale"])
        self.camera_worker = CameraWorker(camera, self.recogniser, config["recognise_every_n"])
        self.camera_worker.frame_ready.connect(self.camera_pane.show_frame)
        self.camera_worker.frame_ready.connect(self.stage.show_camera_frame)
        self.camera_worker.failed.connect(lambda why: self.camera_pane.set_caption(f"Camera failed: {why}", panes.RED))
        self.recogniser.result_ready.connect(self.on_recognition)
        self.camera_note = "SIMULATED CAMERA" if synthetic_camera else ("SIMULATED FACE RECOGNITION" if engine.simulated else "")

        # Card reader (its callback runs on its own thread, so it goes through a signal)
        self.card_scanned.connect(self.on_card)
        self.reader = create_card_reader(config, hardware, self.card_scanned.emit)

        # A strip to type card numbers into when the reader is simulated
        if isinstance(self.reader, SimulatedCardReader):
            self.sim_card = QComboBox()
            self.sim_card.setEditable(True)
            scan = QPushButton("Simulate card scan")
            scan.clicked.connect(lambda: self.reader.inject(self.sim_card.currentText().strip()))
            strip = QHBoxLayout()
            strip.addWidget(self.sim_card, 1)
            strip.addWidget(scan)
            outer.addLayout(strip)

        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.tick)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.exit_app)

    def start(self):
        self.recogniser.start()
        self.camera_worker.start()
        self.reader.start()
        self.tick_timer.start(100)
        self.reset_idle()

    # ---- looks -------------------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        u = max(6.0, self.height() / 100)  # 1% of the window height, so everything scales
        self.setStyleSheet(STYLE.format(
            body=int(2.2 * u), small=int(1.8 * u), tiny=int(1.5 * u), big=int(3.4 * u), radius=int(1.0 * u),
            pad=int(0.8 * u), pad2=int(1.6 * u), pad_s=int(0.4 * u),
            green=panes.GREEN, amber=panes.AMBER, red=panes.RED))

    # ---- shared ------------------------------------------------------------------------------

    def admin_ok(self):
        """Ask for the admin PIN if one is set in the config."""
        pin = self.config["admin_pin"]
        if not pin:
            return True
        text, ok = QInputDialog.getText(self, "Admin PIN", "Enter the admin PIN:", QLineEdit.EchoMode.Password)
        return ok and text == pin

    def switch_mode(self):
        if self.state in SWITCHABLE and self.admin_ok():
            self.mode = "enrol" if self.mode == "vault" else "vault"
            self.reset_idle()

    def exit_app(self):
        if self.state == ENROL_CAPTURE:
            # Capture carries on until enough images are taken or Exit is clicked; nothing is saved
            self.reset_idle()
        elif self.state in SWITCHABLE and self.admin_ok():
            self.close()

    def closeEvent(self, event):
        self.tick_timer.stop()
        self._close_log()
        self.reader.stop()
        self.camera_worker.stop()
        self.recogniser.stop()
        self.camera_worker.camera.close()
        self.hardware.close()
        super().closeEvent(event)

    def set_state(self, state):
        self.state = state
        # Give the camera most of the right hand side while a face is being captured. When enrolling,
        # the camera is in frame 1 and frame 3 is the (long) list of facial features
        info, camera = {FACE: (35, 65), ENROL_CAPTURE: (24, 76)}.get(state, (62, 38))
        self.right.setStretch(0, info)
        self.right.setStretch(1, camera)
        self.info.mode_button.setEnabled(state in SWITCHABLE)
        self.info.exit_button.setEnabled(state in SWITCHABLE or state == ENROL_CAPTURE)

    def set_overlay(self, faces=(), banner="", colour=camera_worker.GREEN, landmarks=()):
        self.camera_worker.overlay = Overlay(list(faces), banner, colour, list(landmarks))

    def caption(self, text, colour="white"):
        note = f"{self.camera_note}\n" if self.camera_note else ""
        self.camera_pane.set_caption(note + text, colour)

    def reset_idle(self):
        """Back to the start for the current mode, waiting for a card."""
        self.session += 1
        self.recogniser.configure(camera_worker.OFF, self.session)
        self._close_log()
        self.set_overlay()
        self.game = self.verifier = self.card = None
        self.enrol = {}
        self.cards = self.store.load_cards()
        if hasattr(self, "sim_card"):
            self.sim_card.clear()
            self.sim_card.addItems([c.card_id for c in self.cards])
        self.hardware.beacon(False)
        self.hardware.clear_display()
        self.camera_pane.show_features(False)
        self.info.show_page(panes.InfoPane.PAGE_INFO)
        if self.mode == "vault":
            self.set_state(IDLE)
            self.stage.show_image(self.config["vault_image"])
            self.info.title.setText("A.N. Other Bank - Vault Security")
            self.info.mode_button.setText("Enrol users")
            self.info.set_steps(VAULT_STEPS)
            self.info.say("Scan your access card to begin",
                          "You must pass 3 factors to open the vault:\n"
                          "1  Something you HAVE - an access card\n"
                          "2  Something you KNOW - a PIN\n"
                          "3  Something you ARE - your face")
            self.hardware.attract_start()
        else:
            self.set_state(ENROL_IDLE)
            self.stage.show_image(self.config["enrol_image"])
            self.info.title.setText("A.N. Other Bank - New employee")
            self.info.mode_button.setText("Open the vault")
            self.info.set_steps(ENROL_STEPS)
            self.info.say("Scan the new access card", "Then enter a name and PIN, and look at the camera.")
            self.hardware.lights(hw.OFF)
        self.info.set_step_states(["active", "pending", "pending"])
        self.caption(self._idle_caption())
        self.hardware.show_text("Place your TAG", 14)
        self.reader.arm()

    def _idle_caption(self):
        return "Camera ready"

    def _open_log(self):
        try:
            self.log_file = open(self.config["face_log"], "a", newline="")
            self.log_writer = csv.writer(self.log_file)
        except OSError:
            self.log_file = self.log_writer = None

    def _close_log(self):
        if self.log_file is not None:
            self.log_file.close()
        self.log_file = self.log_writer = None

    def tick(self):
        """Called every 100ms: countdowns and time limits (enrolment has none: it goes on until the
        training images are captured or Exit is clicked)."""
        if self.state == PIN:
            self.info.pin_game.refresh(self.game)
            if self.game.check_time() == pin_game.OUT_OF_TIME:
                self.fail(2, "You ran out of time")
        elif self.state == FACE:
            self.verifier.tick()
            self._face_status()
            if self.verifier.state == face.FAILED:
                self.fail(3, "Face not recognised in time")
            elif self.verifier.finished:
                self.succeed()

    # ---- card --------------------------------------------------------------------------------

    def on_card(self, card_id):
        self.hardware.show_text("ID : " + card_id, 11, (4, 8), box=True)
        if self.mode == "vault" and self.state == IDLE:
            self.hardware.attract_stop()
            self.cards = self.store.load_cards()
            self.card = next((c for c in self.cards if c.card_id == card_id), None)
            if self.card is None:
                self.fail(1, "Card not recognised")
            else:
                self.info.set_step_states(["done", "active", "pending"])
                self.start_pin()
        elif self.mode == "enrol" and self.state == ENROL_IDLE:
            existing = self.store.get(card_id)
            self.enrol = {"card_id": card_id}
            self.set_state(ENROL_FORM)
            self.info.set_step_states(["done", "active", "pending"])
            self.info.say("Enter your details", "Name, then a PIN twice. Click Submit.")
            self.info.enrol_form.load(card_id, existing.name if existing else None)
            self.info.show_page(panes.InfoPane.PAGE_ENROL)

    # ---- vault: factor 2 ---------------------------------------------------------------------

    def start_pin(self):
        self.set_state(PIN)
        cfg = self.config
        self.game = pin_game.PinGame(self.card.pin, cfg["max_guesses"], cfg["time_limit_seconds"])
        self.game.start()
        self.info.say(f"Hello {self.card.name}", f"Factor 2 - something you KNOW. Work out the {self.game.length} digit PIN.")
        self.info.pin_game.load(self.game)
        self.info.show_page(panes.InfoPane.PAGE_PIN)
        self.hardware.show_text("Enter your PIN", 14)

    def on_guess(self, text):
        if self.state != PIN:
            return
        try:
            self.game.submit(text)
        except ValueError as error:
            self.info.pin_game.show_error(str(error))
            return
        except RuntimeError:
            return
        self.info.pin_game.refresh(self.game)
        if self.game.outcome == pin_game.PASSED:
            self.info.pin_game.lock()
            self.info.set_step_states(["done", "done", "active"])
            self.start_face()
        elif self.game.outcome == pin_game.OUT_OF_GUESSES:
            self.fail(2, "You used all your guesses")

    # ---- vault: factor 3 ---------------------------------------------------------------------

    def start_face(self):
        self.set_state(FACE)
        self.session += 1
        self.verifier = face.FaceVerifier.from_config(self.config)
        self._open_log()
        self.set_overlay()
        self.info.say("Look at the camera", "Factor 3 - something you ARE.")
        self.info.show_page(panes.InfoPane.PAGE_INFO)
        self.recogniser.configure(camera_worker.VERIFY, self.session, claimed=self.card, known=self.cards)
        self.hardware.show_text("Look at the camera", 14)

    def _face_status(self):
        v = self.verifier
        if v.state == face.WAITING:
            self.caption(f"Looking for a face... {v.seconds_left():.0f}s")
        elif v.state == face.VERIFYING:
            self.caption(f"Checking... {v.matches}/{v.vote_required} matches - {v.seconds_left():.0f}s left")
        elif v.state == face.PASSED:
            self.caption("FACE RECOGNISED", panes.GREEN)

    def on_recognition(self, result):
        if result.session != self.session:
            return
        if self.state == FACE and result.mode == camera_worker.VERIFY:
            self.verifier.tick()
            matched = self.verifier.observe(result.face_count, result.best_distance)
            if self.log_writer is not None:
                self.log_writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), self.card.card_id, result.face_count,
                                          "" if result.best_distance is None else round(result.best_distance, 3),
                                          "" if result.face_mean is None else result.face_mean,
                                          "" if result.face_std is None else result.face_std,
                                          int(matched), self.verifier.matches])
            banner = "FACE RECOGNISED - PASSED" if self.verifier.state == face.PASSED else ""
            self.set_overlay(result.faces, banner)
            self._face_status()
        elif self.state == ENROL_CAPTURE and result.mode == camera_worker.ENROL:
            if result.face_count == 1:  # only one person's face goes into the average
                self.enrol["encodings"].append(result.encodings[0])
            total = self.config["training_images"]
            have = len(self.enrol["encodings"])
            self.set_overlay(result.faces, f"Training image {min(have, total)}/{total} captured", landmarks=result.landmarks)
            self.camera_pane.set_features(result.landmarks)
            self.caption("Look at the camera" if result.face_count == 1 else
                         ("Only one face please" if result.face_count > 1 else "No face seen"))
            if have >= total:
                self.save_enrolment()

    # ---- vault: result -----------------------------------------------------------------------

    def _begin_result(self, banner, colour):
        self.set_state(RESULT)
        self.session += 1
        self.recogniser.configure(camera_worker.OFF, self.session)
        self._close_log()
        self.hardware.attract_stop()
        self.info.show_page(panes.InfoPane.PAGE_INFO)
        self.stage.set_banner(banner, colour)

    def succeed(self):
        self._begin_result("ACCESS GRANTED", panes.GREEN)
        self.info.set_step_states(["done", "done", "done"])
        self.info.say("Access granted!", "All security checks are complete.")
        self.caption("FACE RECOGNISED", panes.GREEN)
        self.set_overlay(banner="")
        self.hardware.lights(hw.GREEN)
        self.hardware.show_text("Access granted!", 14)
        self._after_video = lambda: self.hardware.lights(hw.OFF)
        self.stage.play(self.config["granted_video"])

    def fail(self, step, reason):
        if self.state == RESULT:
            return
        self._begin_result("ACCESS DENIED", panes.RED)
        states = ["done" if i < step - 1 else "pending" for i in range(3)]
        states[step - 1] = "failed"
        self.info.set_step_states(states)
        self.info.say("Access denied", f"Authentication failed at factor {step}: {reason}.")
        self.set_overlay()
        self.hardware.show_text("Access denied!", 14)
        self.hardware.beacon(True)
        self.hardware.lights(hw.RED)

        def done():
            self.hardware.beacon(False)
            self.hardware.lights(hw.OFF)
        self._after_video = done
        self.stage.play(self.config["denied_video"])

    def _video_finished(self):
        if self.state != RESULT:
            return
        if self._after_video is not None:
            self._after_video()
            self._after_video = None
        self.hardware.clear_display()
        QTimer.singleShot(2000, self._reset_after_result)  # the banner stays up for 2 seconds

    def _reset_after_result(self):
        if self.state == RESULT:
            self.reset_idle()

    # ---- enrolment ---------------------------------------------------------------------------

    def on_enrol_submitted(self, name, pin, pin_again):
        if self.state != ENROL_FORM:
            return
        form, length = self.info.enrol_form, self.config["pin_length"]
        if not name:
            form.show_error("Name cannot be blank")
        elif not pin_game.is_valid_pin(pin, length):
            form.show_error(f"Please enter a valid {length}-digit PIN", clear_pins=True)
        elif pin != pin_again:
            form.show_error("The PINs do not match, try again", clear_pins=True)
        else:
            total = self.config["training_images"]
            self.enrol.update(name=name, pin=pin, encodings=[])
            self.set_state(ENROL_CAPTURE)
            self.session += 1
            form.set_enabled(False)
            self.info.set_step_states(["done", "done", "active"])
            self.info.say("Look at the camera", "Keep your face in view and watch your features being found. Click Exit to stop.")
            self.info.show_page(panes.InfoPane.PAGE_INFO)  # the count is on the live view
            self.stage.show_live()  # the big live view, in frame 1
            self.camera_pane.show_features(True)
            self.camera_pane.set_features([])
            self.set_overlay(banner=f"Training image 0/{total} captured")
            self.recogniser.configure(camera_worker.ENROL, self.session)

    def save_enrolment(self):
        self.recogniser.configure(camera_worker.OFF, self.session)
        e = self.enrol
        self.store.save(Card(e["card_id"], e["name"], e["pin"], np.mean(e["encodings"], axis=0)))
        self.set_state(RESULT)
        self.info.set_step_states(["done", "done", "done"])
        self.info.say("Saved", f"{e['name']} is enrolled with card {e['card_id']}.")
        self.info.show_page(panes.InfoPane.PAGE_INFO)
        self.camera_pane.show_features(False)
        self.stage.show_image(self.config["enrol_image"], "USER ENROLLED", panes.GREEN)
        self.set_overlay()
        self.hardware.beep()
        QTimer.singleShot(3000, self._reset_after_result)


def main():
    parser = argparse.ArgumentParser(description="Can you break the bank? - vault and enrolment in one window")
    parser.add_argument("--mode", choices=("vault", "enrol"), help="start in this mode (overrides [app] mode)")
    parser.add_argument("--windowed", action="store_true", help="run in a window instead of fullscreen")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

    config = load_config()
    if args.mode:
        config["app_mode"] = args.mode
    if args.windowed:
        config["fullscreen"] = False

    app = QApplication(sys.argv)
    hardware = hw.create_hardware(config)
    if not isinstance(hardware, hw.SimulatedHardware):
        # On a real Pi nothing may silently fall back to a stand-in (a synthetic camera, the
        # simulated face engine or an empty in-memory store): a missing piece is an error, and
        # the kiosk wrapper (run_vault.sh) restarts the app
        config["hardware_backend"] = "real"
    engine = create_face_engine(config)
    camera, synthetic_camera = open_app_camera(config)
    store, in_memory = create_store(config)
    if in_memory and engine.simulated:
        # With nothing enrolled a developer couldn't get past the first factor
        from face_engine import SimulatedFaceEngine
        store.save(Card("SIMCARD0001", "Demo User", "1234", SimulatedFaceEngine.BASE))

    window = MainWindow(config, hardware, store, engine, camera, synthetic_camera)
    if config["fullscreen"]:
        window.showFullScreen()
    else:
        width, height = (int(v) for v in config["window_size"].lower().split("x"))
        window.resize(width, height)
        window.show()
    window.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
