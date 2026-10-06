"""
app_config.py

Shared settings for the PiFace scripts, read from
~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg (see can-you-break-the-bank.cfg.example).

Every setting has a default matching the original hard-coded value, so a missing
config file or a missing option behaves as it did before the config file existed.

Single or dual node mode is worked out from the [redis] section:
  - remote_host set   -> dual node mode (two Pis, kept in step by redis-sync.py)
  - remote_host empty
    or missing        -> single node mode (one Pi, local Redis only)
"""

import configparser
import os
import sys

CONFIG_PATH = os.path.expanduser("~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg")

DEFAULT_LOCAL_HOST = "127.0.0.1"
DEFAULT_PORT = 6379

CAMERA_TYPES = ("picamera", "webcam")


def load_config(path=CONFIG_PATH):
    """Return the settings as a flat dict (see the keys below).

    Paths in the [paths] section are resolved against base_dir unless they are absolute.
    """
    parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    if not parser.read(path):
        print(f"[warn] Config file {path} not found - using the default settings "
              f"(single node mode, local Redis on {DEFAULT_LOCAL_HOST}:{DEFAULT_PORT})", file=sys.stderr)

    def get(section, option, default):
        return parser.get(section, option, fallback=default).strip()

    def get_int(section, option, default):
        return parser.getint(section, option, fallback=default)

    def get_float(section, option, default):
        return parser.getfloat(section, option, fallback=default)

    remote_host = get("redis", "remote_host", "") or None

    camera_type = get("camera", "type", "picamera").lower()
    if camera_type not in CAMERA_TYPES:
        raise ValueError(f"[camera] type must be one of {CAMERA_TYPES}, not '{camera_type}'")

    base_dir = get("paths", "base_dir", "/home/pi/PiFace")

    def get_path(option, default):
        # os.path.join keeps an absolute value as it is
        return os.path.join(base_dir, get("paths", option, default))

    return {
        # [redis]
        "local_host": get("redis", "local_host", DEFAULT_LOCAL_HOST) or DEFAULT_LOCAL_HOST,
        "local_port": get_int("redis", "local_port", DEFAULT_PORT),
        "remote_host": remote_host,
        "remote_port": get_int("redis", "remote_port", DEFAULT_PORT),
        "dual": remote_host is not None,

        # [camera]
        "camera_type": camera_type,
        "webcam_device": get("camera", "webcam_device", "/dev/video0"),
        "frame_width": get_int("camera", "frame_width", 640),
        "frame_height": get_int("camera", "frame_height", 480),
        "frame_rate": get_int("camera", "frame_rate", 30),

        # [enrolment]
        "training_images": get_int("enrolment", "training_images", 10),

        # [pin]
        "pin_length": get_int("pin", "pin_length", 4),
        "max_guesses": get_int("pin", "max_guesses", 5),
        "time_limit_seconds": get_int("pin", "time_limit_seconds", 45),

        # [face_recognition]
        "match_threshold": get_float("face_recognition", "match_threshold", 0.55),
        "vote_window": get_int("face_recognition", "vote_window", 8),
        "vote_required": get_int("face_recognition", "vote_required", 5),
        "recognise_every_n": get_int("face_recognition", "recognise_every_n", 3),
        "small_frame_scale": get_float("face_recognition", "small_frame_scale", 0.25),
        "timer_seconds": get_int("face_recognition", "timer_seconds", 10),
        "face_wait_seconds": get_int("face_recognition", "face_wait_seconds", 30),
        "pass_hold_seconds": get_int("face_recognition", "pass_hold_seconds", 3),

        # [hardware]
        "beacon_pin": get_int("hardware", "beacon_pin", 26),
        "buzzer_pin": get_int("hardware", "buzzer_pin", 17),
        "serial_port": get("hardware", "serial_port", "/dev/ttyS0"),
        "neopixel_count": get_int("hardware", "neopixel_count", 56),
        "neopixel_brightness": get_float("hardware", "neopixel_brightness", 1),
        "neopixel_frequency": get_int("hardware", "neopixel_frequency", 3200000),

        # [paths]
        "base_dir": base_dir,
        "includes_dir": get_path("includes_dir", "includes"),
        "vault_wallpaper": get_path("vault_wallpaper", "Images/bankvault_background.png"),
        "exit_wallpaper": get_path("exit_wallpaper", "Images/CanYouBreakTheBank.jpg"),
        "enrol_wallpaper": get_path("enrol_wallpaper", "Images/facial_recognition.jpg"),
        "granted_video": get_path("granted_video", "Images/granted.mp4"),
        "denied_video": get_path("denied_video", "Images/denied.mp4"),
        "oled_logo": get_path("oled_logo", "includes/SB.png"),
        "face_log": get_path("face_log", "face_log.csv"),
        "pin_game": get_path("pin_game", "secret-number.py"),
    }
