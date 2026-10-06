# Can You Break the Bank?

An activity built on Raspberry Pi to demonstrate multi-factor authentication to
students as part of STEM engagement. It's easier to see what it does than to
explain it: [demo videos](https://www.youtube.com/playlist?list=PLIR_HrJp_obj0JJrIxTPFZh3l3DSfxZHo).

Players try to open the vault of "A.N. Other Bank" by passing three security checks:

| Factor | Type | Implementation |
|--------|------|----------------|
| 1 | Something you **have** | Scan an RFID access card |
| 2 | Something you **know** | Guess the card owner's PIN in a Wordle-style game (by default 4 digits, 5 guesses, 45 seconds) |
| 3 | Something you **are** | Face recognition must match the owner of the scanned card |

Success plays a vault-opening video; failure sounds the beacon, turns the
NeoPixels red and plays an access-denied video.

## Hardware

- Raspberry Pi running KDE Plasma, with an external screen connected over HDMI
- Pi camera (CSI) via `picamera2`, or a USB webcam
- RFID reader HAT on `/dev/ttyS0` (9600 baud, 12-char tags) with buzzer on GPIO 17
- SSD1306 128x32 OLED over I2C (address `0x3c`)
- 56-pixel NeoPixel strip on SPI
- 12V flashing beacon via relay on GPIO 26

## Software

Python 3 with: `face_recognition`, `opencv-python`, `numpy`, `Pillow`, `picamera2`,
`redis`, `pyserial`, `RPi.GPIO`, `smbus`/`smbus2`, `adafruit-circuitpython-neopixel-spi`,
`dbus-python`, plus `ffplay` (ffmpeg) for video playback and a local Redis server.

**OpenCV (`cv2`) and dlib must both be installed.** OpenCV handles the camera frames and the
on-screen video; dlib does the face detection and encoding and is built when you install
`face_recognition`. The build is slow on a Pi - see [SETUP.md](SETUP.md).

The scripts expect to live at `/home/pi/PiFace/` on the Pi by default (see Configuration).
[SETUP.md](SETUP.md) walks through setting up a new Pi.

## Scripts

| File | Purpose |
|------|---------|
| `tk_add_user.py` | Enrol a user: scan card, enter name and PIN, capture face encodings, save to Redis |
| `tk_open_vault.py` | Main game UI running the three factors |
| `secret-number.py` | Factor 2 mini-game; exit code 1 = success, 0 = failure |
| `includes/oled_091.py` | SSD1306 OLED driver from SB Components (not in git - see Repository notes) |
| `read_rfid.py` | Standalone RFID tag reader (prints scanned IDs on Ctrl+C) |
| `change_wallpaper.py` | Set the KDE wallpaper via D-Bus |
| `app_config.py` | Reads the settings (Redis, camera, tuning, pins, paths) and single/dual node mode from the config file |
| `camera_setup.py` | Opens the camera for both apps: the Pi camera, or a USB webcam (`[camera] type = webcam`) |
| `redis-sync.py` | Two-way sync of Redis between two Pis (runs as a systemd service; exits in single node mode) |
| `show_all_keys.py` | Dump all keys on the local Redis (and the remote one in dual node mode) |
| `delete_all_redis_keys.py` | Wipe the local Redis (and the remote one in dual node mode); `--stop-service` / `--start-service` yes\|no |
| `reset_all_redis.sh` | Stops the sync service, runs `delete_all_redis_keys.py`, then restarts the service |
| `retrieve_redis.py` | Example of storing and retrieving user data (demo only) |
| `can-you-break-the-bank.cfg.example` | Template for the per-Pi config file (see Configuration) |
| `redis.service`, `redis-sync.service` | systemd units for Redis and the Redis sync |

## Data model

Each user is a Redis hash at `card:<RFID id>` with fields `name`, `pin` and
`encoding` (a pickled 128-d face encoding).

## Configuration

Each Pi reads `~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg` (copy
`can-you-break-the-bank.cfg.example`). Every setting is optional and defaults to the original
value. The file covers the Redis hosts, camera (Pi camera or USB webcam), face recognition
tuning, enrolment, GPIO pins, NeoPixels and file paths.

- **Two Pis (dual node mode):** set `remote_host` in `[redis]` to the *other* Pi's IP address.
- **One Pi (single node mode):** leave `remote_host` empty. `redis-sync.py` then has nothing to sync and exits.

## Usage

```
python3 tk_add_user.py    # enrol users
python3 tk_open_vault.py  # run the game
```

## Licence

GPL-3.0 - see [LICENSE](LICENSE).

## Repository notes

`includes/` is git-ignored for now (mixed licensing). It holds the SB Components RFID HAT files
(`oled_091.py`, `SB.png` and `Fonts/`) and must be present on the Pi for the game to run, along
with `Images/` from this repo.
