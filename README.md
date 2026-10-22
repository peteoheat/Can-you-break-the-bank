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

The whole activity runs in one full-screen window (`vault_app.py`):

- **Frame 1 (left 70%):** the closed vault, the "ACCESS GRANTED / DENIED" banner and the
  granted/denied videos (with sound). When enrolling a user it becomes a large live camera view,
  with the face and its features (eyes, nose, lips, chin...) drawn on as they are found.
- **Frame 2 (top right):** progress through the three factors, instructions, and the PIN game
  (or the enrolment form).
- **Frame 3 (bottom right):** the live camera with face recognition feedback. When enrolling, it
  lists each facial feature found and its coordinates instead.

The **Enrol users / Open the vault** button in frame 2 switches between playing the game and
adding users, so either Pi can do either job. The layout scales to the screen, from 800x600 to 4K.

## Hardware

- Raspberry Pi running KDE Plasma, with an external screen connected over HDMI
- Pi camera (CSI) via `picamera2`, or a USB webcam
- RFID reader HAT on `/dev/ttyS0` (9600 baud, 12-char tags) with buzzer on GPIO 17
- SSD1306 128x32 OLED over I2C (address `0x3c`)
- 56-pixel NeoPixel strip on SPI
- 12V flashing beacon via relay on GPIO 26

## Software

Python 3 (Raspberry Pi OS Bookworm, Python 3.11) with: `PyQt6` (apt, including its multimedia
module and GStreamer, which play the videos), `face_recognition`, `opencv` (apt `python3-opencv`),
`numpy`, `picamera2`, `redis`, `pyserial`, `RPi.GPIO`, `smbus`/`smbus2`,
`adafruit-circuitpython-neopixel-spi`, and a local Redis server.

**OpenCV (`cv2`) and dlib must both be installed.** OpenCV handles the camera frames; dlib does
the face detection and encoding and is built when you install `face_recognition`. The build is
slow on a Pi - see [SETUP.md](SETUP.md).

The app can also run on a development machine (for example Windows) with just PyQt6, OpenCV and
numpy: with `[hardware] backend = auto` (the default) it falls back to simulated hardware, a
synthetic camera and an in-memory store when the Pi pieces aren't there.

Clone the repository into your home directory (it creates `~/Can-you-break-the-bank`); the
scripts work out where they are installed. The config file lives at
`~/.config/can-you-break-the-bank/` (see Configuration). [SETUP.md](SETUP.md) walks through
setting up a new Pi.

## Scripts

| File | Purpose |
|------|---------|
| `vault_app.py` | The application: the vault game and user enrolment in one window (PyQt6) |
| `panes.py` | The three frames of the window and the widgets in them |
| `pin_game.py` | Factor 2 logic: the Wordle-style PIN game |
| `face.py` | Factor 3 logic: the vote that decides whether the face matches |
| `face_engine.py` | Face detection and comparison (`face_recognition`, or a simulated engine) |
| `camera_worker.py` | Camera and recognition threads that feed frame 3 |
| `rfid.py` | Reads access cards on a background thread |
| `hardware.py` | Buzzer, beacon, NeoPixels and OLED, with a simulated version for development |
| `store.py` | Reads and writes users in Redis |
| `includes/oled_091.py` | SSD1306 OLED driver from SB Components (not in git - see Repository notes) |
| `read_rfid.py` | Standalone RFID tag reader (prints scanned IDs on Ctrl+C) |
| `app_config.py` | Reads the settings (Redis, camera, tuning, pins, paths) and single/dual node mode from the config file |
| `camera_setup.py` | Opens the camera: the Pi camera, or a USB webcam (`[camera] type = webcam`) |
| `redis-sync.py` | Two-way sync of Redis between two Pis (runs as a systemd service; exits in single node mode) |
| `show_all_keys.py` | Dump all keys on the local Redis (and the remote one in dual node mode) |
| `delete_all_redis_keys.py` | Wipe the local Redis (and the remote one in dual node mode); `--stop-service` / `--start-service` yes\|no |
| `reset_all_redis.sh` | Stops the sync service, runs `delete_all_redis_keys.py`, then restarts the service |
| `retrieve_redis.py` | Example of storing and retrieving user data (demo only) |
| `run_vault.sh` | Runs `vault_app.py` as a kiosk and restarts it if it crashes (used by the autostart entry) |
| `can-you-break-the-bank.desktop.template` | Template for the autostart entry that launches the app at boot (see SETUP.md) |
| `tests/` | Unit tests for the logic modules: `python -m unittest` from the repo root |
| `can-you-break-the-bank.cfg.example` | Template for the per-Pi config file (see Configuration) |
| `redis.service`, `redis-sync.service.template` | systemd units for Redis and the Redis sync (the sync one is a template - see SETUP.md) |

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
# from the clone, using the venv's Python (see SETUP.md)
.venv/bin/python vault_app.py                 # starts in the mode set by [app] mode (vault by default)
.venv/bin/python vault_app.py --mode enrol    # start in enrol mode
.venv/bin/python vault_app.py --windowed      # a window instead of full screen (for development)
```

Use the button at the top of frame 2 to switch between **Enrol users** and **Open the vault**.
If `admin_pin` is set in the `[app]` section of the config, switching mode or exiting asks for it.

To start the game automatically when the Pi powers on, see "Start the game automatically at boot"
in [SETUP.md](SETUP.md).

- **Vault mode:** scan a card, solve the PIN game, then look at the camera.
- **Enrol mode:** scan the new card, enter a name and a PIN twice, then look at the camera while
  the face is captured. The live view fills frame 1 and shows the features being found. Capture
  goes on until the required number of images has been taken, however long that takes, or until
  you click Exit (which cancels without saving). The user is saved automatically.

## Licence

GPL-3.0 - see [LICENSE](LICENSE).

## Repository notes

`includes/` is git-ignored for now (mixed licensing). It holds the SB Components RFID HAT files
(`oled_091.py`, `SB.png` and `Fonts/`). They are only needed for the OLED display: a Pi without
them still runs the game, just without the OLED messages. `Images/` comes with this repo.
