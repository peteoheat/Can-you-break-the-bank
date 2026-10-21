"""
panes.py

The three frames of the single window, and the widgets inside them:

  StagePane   frame 1: the vault (closed, or granted/denied banner) and the granted/denied videos.
  InfoPane    frame 2: step progress, instructions, and either the PIN game or the enrolment form.
  CameraPane  frame 3: the live camera feed and recognition feedback.

Nothing here knows about hardware, Redis or recognition: the panes show what they are told and
emit signals for what the user does. Sizes are proportional (the main window sets the font sizes
from its height with a stylesheet, see vault_app.py) so the layout works from 800x600 to 4K.
"""

import os

from PyQt6.QtCore import Qt, QRectF, QRegularExpression, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap, QRegularExpressionValidator
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
                             QStackedWidget, QVBoxLayout, QWidget)

import pin_game

WALL = "#454a68"  # the colour of the wall either side of the vault door, for letterbox bars
GREEN = "#27e512"
AMBER = "#f0a020"
RED = "#e03030"
GREY = "#4c4c4c"
STATUS_COLOURS = {pin_game.CORRECT: GREEN, pin_game.MISPLACED: AMBER, pin_game.WRONG: GREY}


class StageImage(QWidget):
    """A picture filling the frame (cropped to fit, so the centre stays), with an optional banner."""

    def __init__(self):
        super().__init__()
        self._pixmap = QPixmap()
        self._banner = ""
        self._banner_colour = QColor(GREEN)

    def set_image(self, path):
        self._pixmap = QPixmap(path)
        self.update()

    def set_banner(self, text="", colour=GREEN):
        self._banner, self._banner_colour = text, QColor(colour)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(WALL))
        if not self._pixmap.isNull():
            scale = max(self.width() / self._pixmap.width(), self.height() / self._pixmap.height())
            w, h = self._pixmap.width() * scale, self._pixmap.height() * scale
            painter.drawPixmap(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h),
                               self._pixmap, QRectF(self._pixmap.rect()))
        if self._banner:
            band = QRectF(0, self.height() * 0.42, self.width(), self.height() * 0.16)
            fill = QColor(self._banner_colour)
            fill.setAlpha(225)
            painter.fillRect(band, fill)
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(int(band.height() * 0.5))
            painter.setFont(font)
            painter.setPen(QColor("white"))
            painter.drawText(band, Qt.AlignmentFlag.AlignCenter, self._banner)


class StagePane(QFrame):
    """Frame 1. Shows the vault image, or plays a video (with sound) in its place."""

    video_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("stage")
        self.image = StageImage()
        self.video = QVideoWidget()
        self.video.setStyleSheet(f"background: {WALL};")
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.mediaStatusChanged.connect(self._status_changed)
        self.player.errorOccurred.connect(self._error)
        self._playing = False
        self.pages = QStackedWidget()
        self.pages.addWidget(self.image)
        self.pages.addWidget(self.video)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.pages)

    def show_image(self, path, banner="", colour=GREEN):
        self.player.stop()
        self.image.set_image(path)
        self.image.set_banner(banner, colour)
        self.pages.setCurrentWidget(self.image)

    def set_banner(self, text="", colour=GREEN):
        self.image.set_banner(text, colour)

    def play(self, path):
        """Play a video in the frame, then emit video_finished (also if it can't be played)."""
        self._playing = True
        if not os.path.exists(path):
            QTimer.singleShot(0, self._finish)
            return
        self.pages.setCurrentWidget(self.video)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def _status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._finish()

    def _error(self, error, message):
        self._finish()

    def _finish(self):
        if self._playing:
            self._playing = False
            self.pages.setCurrentWidget(self.image)
            self.video_finished.emit()


class GuessGrid(QWidget):
    """The Wordle-style grid: one row per allowed guess, coloured by how each digit scored."""

    def __init__(self):
        super().__init__()
        self.length = 4
        self.rows = 5
        self.guesses = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_state(self, length, rows, guesses):
        self.length, self.rows, self.guesses = length, rows, list(guesses)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gap = 0.1
        cell = min(self.width() / (self.length + gap * (self.length - 1)),
                   self.height() / (self.rows + gap * (self.rows - 1)))
        left = (self.width() - cell * (self.length + gap * (self.length - 1))) / 2
        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(int(cell * 0.55))
        painter.setFont(font)
        for row in range(self.rows):
            top = row * cell * (1 + gap)
            for column in range(self.length):
                rect = QRectF(left + column * cell * (1 + gap), top, cell, cell)
                if row < len(self.guesses):
                    status, digit = self.guesses[row][1][column]
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(STATUS_COLOURS[status]))
                    painter.drawRoundedRect(rect, cell * 0.12, cell * 0.12)
                    painter.setPen(QColor("white" if status == pin_game.WRONG else "black"))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, digit)
                else:
                    painter.setPen(QPen(QColor("#5a6572"), max(1, cell * 0.03)))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(rect, cell * 0.12, cell * 0.12)


class PinGameWidget(QWidget):
    """Factor 2 in frame 2: countdown, entry box, guess grid and a key to the colours."""

    guess_submitted = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.timer_label = QLabel("")
        self.timer_label.setObjectName("timer")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entry = QLineEdit()
        self.entry.setObjectName("entry")
        self.entry.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]*"), self.entry))
        self.entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entry.returnPressed.connect(self._submit)
        self.button = QPushButton("Submit")
        self.button.setObjectName("go")
        self.button.clicked.connect(self._submit)
        self.error_label = QLabel("")
        self.error_label.setObjectName("error")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grid = GuessGrid()
        self.attempts_label = QLabel("")
        self.attempts_label.setObjectName("detail")
        self.attempts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        legend = QHBoxLayout()
        for colour, text in ((GREEN, "Right place"), (AMBER, "Wrong place"), (GREY, "Not in PIN")):
            key = QLabel(text)
            key.setObjectName("legend")
            key.setAlignment(Qt.AlignmentFlag.AlignCenter)
            key.setStyleSheet(f"background: {colour}; color: {'white' if colour == GREY else 'black'};")
            legend.addWidget(key)
        entry_row = QHBoxLayout()
        entry_row.addWidget(self.entry, 3)
        entry_row.addWidget(self.button, 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for item in (self.timer_label, entry_row, self.error_label, self.grid, self.attempts_label, legend):
            if isinstance(item, QWidget):
                layout.addWidget(item, 1 if item is self.grid else 0)
            else:
                layout.addLayout(item)
        self._length = 4

    def load(self, game):
        self._length = game.length
        self.entry.setMaxLength(game.length)
        self.entry.setPlaceholderText(f"{game.length} digits")
        self.entry.clear()
        self.entry.setEnabled(True)
        self.button.setEnabled(True)
        self.show_error("")
        self.entry.setFocus()
        self.refresh(game)

    def refresh(self, game):
        seconds = game.remaining_seconds()
        self.timer_label.setText(f"{int(seconds // 60):02d}:{seconds % 60:04.1f}")
        self.grid.set_state(game.length, game.max_guesses, game.guesses)
        self.attempts_label.setText(f"Attempts: {len(game.guesses)}/{game.max_guesses}")

    def show_error(self, text):
        self.error_label.setText(text)
        self.error_label.setVisible(bool(text))

    def lock(self):
        self.entry.setEnabled(False)
        self.button.setEnabled(False)

    def _submit(self):
        text = self.entry.text()
        self.entry.clear()
        self.show_error("")
        self.guess_submitted.emit(text)
        self.entry.setFocus()


class EnrolForm(QWidget):
    """Enrolment in frame 2: name and PIN (twice), then progress while the face is captured."""

    submitted = pyqtSignal(str, str, str)  # name, pin, pin again
    cancelled = pyqtSignal()

    def __init__(self, pin_length):
        super().__init__()
        self.card_label = QLabel("")
        self.card_label.setObjectName("detail")
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name")
        self.pin = QLineEdit()
        self.pin.setPlaceholderText(f"{pin_length} digit PIN")
        self.pin_again = QLineEdit()
        self.pin_again.setPlaceholderText("Re-enter PIN")
        for entry in (self.pin, self.pin_again):
            entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.error_label = QLabel("")
        self.error_label.setObjectName("error")
        self.error_label.setWordWrap(True)
        self.submit = QPushButton("Submit")
        self.submit.setObjectName("go")
        self.cancel = QPushButton("Cancel")
        self.submit.clicked.connect(self._submit)
        self.cancel.clicked.connect(self.cancelled)
        for entry in (self.name, self.pin, self.pin_again):
            entry.setObjectName("entry")
            entry.returnPressed.connect(self._submit)
        buttons = QHBoxLayout()
        buttons.addWidget(self.submit)
        buttons.addWidget(self.cancel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for widget in (self.card_label, self.name, self.pin, self.pin_again, self.error_label):
            layout.addWidget(widget)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def load(self, card_id, existing_name=None):
        self.card_label.setText(f"Card {card_id}" + (f" (currently {existing_name} - saving will replace it)" if existing_name else ""))
        for entry in (self.name, self.pin, self.pin_again):
            entry.clear()
        self.error_label.setText("")
        self.set_enabled(True)
        self.name.setFocus()

    def set_enabled(self, enabled):
        for widget in (self.name, self.pin, self.pin_again, self.submit):
            widget.setEnabled(enabled)

    def show_error(self, text, clear_pins=False):
        self.error_label.setText(text)
        if clear_pins:
            self.pin.clear()
            self.pin_again.clear()
            self.pin.setFocus()

    def _submit(self):
        self.submitted.emit(self.name.text().strip(), self.pin.text(), self.pin_again.text())


class InfoPane(QFrame):
    """Frame 2. Step chips, instruction text, and the PIN game or the enrolment form."""

    mode_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    PAGE_INFO, PAGE_PIN, PAGE_ENROL = 0, 1, 2

    def __init__(self, pin_length):
        super().__init__()
        self.setObjectName("info")
        self.title = QLabel("A.N. Other Bank")
        self.title.setObjectName("title")
        self.mode_button = QPushButton("Enrol users")
        self.mode_button.setObjectName("small")
        self.mode_button.clicked.connect(self.mode_requested)
        self.exit_button = QPushButton("Exit")
        self.exit_button.setObjectName("small")
        self.exit_button.clicked.connect(self.exit_requested)
        top = QHBoxLayout()
        top.addWidget(self.title, 1)
        top.addWidget(self.mode_button)
        top.addWidget(self.exit_button)

        self.chips = [QLabel() for _ in range(3)]
        chip_row = QHBoxLayout()
        for chip in self.chips:
            chip.setObjectName("chip")
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip_row.addWidget(chip)

        self.instruction = QLabel("")
        self.instruction.setObjectName("instruction")
        self.instruction.setWordWrap(True)
        self.detail = QLabel("")
        self.detail.setObjectName("detail")
        self.detail.setWordWrap(True)

        self.pin_game = PinGameWidget()
        self.enrol_form = EnrolForm(pin_length)
        self.progress = QLabel("")
        self.progress.setObjectName("detail")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.progress)
        self.pages.addWidget(self.pin_game)
        self.pages.addWidget(self.enrol_form)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(chip_row)
        layout.addWidget(self.instruction)
        layout.addWidget(self.detail)
        layout.addWidget(self.pages, 1)

    def set_steps(self, labels):
        for chip, label in zip(self.chips, labels):
            chip.setText(label)
        self.set_step_states(["pending"] * 3)

    def set_step_states(self, states):
        """Each of "pending", "active", "done" or "failed"."""
        for chip, state in zip(self.chips, states):
            chip.setProperty("state", state)
            chip.style().unpolish(chip)
            chip.style().polish(chip)

    def say(self, instruction, detail=""):
        self.instruction.setText(instruction)
        self.detail.setText(detail)

    def show_page(self, page, text=""):
        self.progress.setText(text)
        self.pages.setCurrentIndex(page)


class CameraPane(QFrame):
    """Frame 3. The live feed, scaled to fit, with a caption underneath."""

    def __init__(self):
        super().__init__()
        self.setObjectName("camera")
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.caption = QLabel("")
        self.caption.setObjectName("caption")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self._image = None
        layout = QVBoxLayout(self)
        layout.addWidget(self.picture, 1)
        layout.addWidget(self.caption)

    def show_frame(self, image: QImage):
        self._image = image
        self._paint()

    def set_caption(self, text, colour="white"):
        self.caption.setText(text)
        self.caption.setStyleSheet(f"color: {colour};")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._paint()

    def _paint(self):
        if self._image is not None:
            self.picture.setPixmap(QPixmap.fromImage(self._image).scaled(
                self.picture.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
