# CLAUDE.md

Raspberry Pi three-factor-auth vault game (RFID card, Wordle-style PIN, face recognition). See README.md for the overview.

## Environment
- Code runs on a Raspberry Pi (KDE, Python 3) from a clone of the repo in the user's home directory (`~/can-you-break-the-bank`). Don't hard-code that path anywhere: `app_config.py` defaults `base_dir` to the folder it lives in, and the paths to videos, images and `includes/` are resolved against it (overridable in the `[paths]` section of the config file - see Configuration). Development happens on Windows, so the hardware modules (`RPi.GPIO`, `picamera2`, `neopixel_spi`, `board`, `dbus`, `smbus`) can't be imported or run here - review and edit only, don't try to execute the scripts.
- Each Pi drives an external HDMI screen (not a touchscreen); the Tkinter windows are fixed at 800x600 at the top-left (`+0+0`).
- No tests, build step or package manifest.
- `Images/` is tracked in git (all copyright material has been removed). `includes/` is git-ignored (mixed licensing, deal with later) - don't add or commit its contents. It holds the SB Components RFID HAT files: `oled_091.py` (the smbus2 variant, provided by SB Components - don't modify it), `SB.png` and `Fonts/`. `oled_091.py` loads its font from `Fonts/` next to itself, so `Fonts/` must stay inside `includes/`. These files are only relevant if the SB Components HAT is the one in use.

## Deployment modes
The activity runs in one of two ways:
- **Single Pi:** alternate between `tk_add_user.py` (enrol users) and `tk_open_vault.py` (the game) on the same Pi, using its local Redis.
- **Two Pis:** normally enrolment runs on **PiFace1** (`192.168.8.152`) and the game on **PiFace2** (`192.168.8.153`). `redis-sync.py` replicates Redis between them and must stay **bi-directional**, so either Pi can do either job - e.g. PiFace1 can run the game when the enrolment queue is short but the game queue is long.

The mode is set per Pi by the `[redis]` section of the config file. A `remote_host` means dual node mode and should be the *other* Pi's IP, so the two Pis have different configs and no IP addresses are hard-coded in the scripts. No `remote_host` (or no config file) means single node mode.

## Configuration
Settings live in `~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg` (template: `can-you-break-the-bank.cfg.example`), read by `app_config.py` (`load_config()` returns a flat dict). Every option is optional and defaults to the original hard-coded value. Sections: `[redis]`, `[camera]`, `[enrolment]`, `[pin]`, `[face_recognition]`, `[hardware]`, `[paths]`. `[pin] pin_length` is shared by `secret-number.py` and the enrolment checks in `tk_add_user.py`. When adding a setting, add it to `app_config.py` (with its default) and to the example file rather than hard-coding it in a script.

`[camera] type` is `picamera` (Pi camera via Picamera2, imported only when used) or `webcam` (USB webcam). Both apps open the camera with `open_camera(config)` from `camera_setup.py`, so they set it up identically (the Pi camera uses the preview configuration with the configured frame rate). Both camera types provide `capture_array()`/`close()` and give BGR frames, so the colour handling is the same. Don't duplicate the camera setup in a script.

## Architecture
- `tk_open_vault.py`: Tkinter `AuthApp`. Factor 1 reads RFID from the configured serial port (`/dev/ttyS0` by default); Factor 2 shells out to `secret-number.py <pin>` and treats a truthy exit code as a pass (exit 1 = success, 0 = failure - intentional, keep it); Factor 3 loops camera frames (the `timer_seconds` timer starts on the first detected face; gives up after `face_wait_seconds` with no face) and passes early when `vote_required` of the last `vote_window` recognition passes matched (distance <= `match_threshold`), then holds the live video for `pass_hold_seconds` with a "PASSED" banner. The vote is 1:1 against the scanned card's enrolled encoding, so other faces in frame never affect it; boxes are green (this card), amber (another enrolled card) or red (not recognised). Detection/encoding runs on every `recognise_every_n`th frame, and each pass is one vote. Frames are converted BGR to RGB before encoding, as in enrolment (the camera's "RGB888" frames are BGR in memory) - keep the two apps in step or distances rise. Every pass is appended to `face_log.csv` (path in the config, git-ignored) for tuning the `[face_recognition]` settings.
- `tk_add_user.py`: enrolment. Averages `training_images` (10 by default) face encodings and stores a hash at `card:<id>` (`name`, `pin`, pickled `encoding`) in local Redis.
- `app_config.py`: shared config loader (see Configuration), including the single/dual node mode. Used by `redis-sync.py`, `delete_all_redis_keys.py`, `show_all_keys.py`, `tk_open_vault.py`, `tk_add_user.py`, `secret-number.py`, `read_rfid.py` and `change_wallpaper.py`. It must be deployed alongside them, as must `camera_setup.py` (used by `tk_open_vault.py` and `tk_add_user.py`).
- `redis-sync.py` replicates the local Redis to a second Pi via keyspace events. In single node mode it logs and exits 0 (`redis-sync.service` uses `Restart=on-failure` so systemd leaves it stopped). `delete_all_redis_keys.py` and `show_all_keys.py` act on the local Redis, plus the remote one in dual node mode; the delete script ignores `--stop-service`/`--start-service` in single node mode. `reset_all_redis.sh` stops `redis-sync.service`, runs the delete script from its own directory, then restarts the service.
- `redis.service` is a reference copy of the Redis unit. `redis-sync.service.template` is the template for the sync unit: it has `@USER@` and `@INSTALL_DIR@` placeholders because systemd units need absolute paths and can't use `~`; SETUP.md installs it with a `sed` command to `/etc/systemd/system/redis-sync.service` (run `sudo systemctl daemon-reload` after changing it). The unit sets no remote host - that comes from each Pi's config file, and a Pi with no config file silently runs in single node mode (sync stops), so create the config on every Pi.
- The camera, GPIO, NeoPixel and OLED are initialised at module import time, so importing these files has hardware side effects.

## Conventions
- The existing code is plain procedural/Tkinter style with 4-space indentation; match it. Settings come from the config file via `app_config.py` (don't hard-code IPs, pins, paths or tuning values); `delete_all_redis_keys.py` still takes the Redis DB number and password from env vars.
- The remote Redis IP differs between the two Pis' config files because each is configured for the *other* Pi (see Deployment modes). `redis-sync.py` runs as a systemd service (`redis-sync.service`) on **both** Pis, each pointing at the other Pi, which is what makes the sync bi-directional. Don't change the sync design in a way that makes it one-directional.
- `delete_all_redis_keys.py` is destructive (flushes the local Redis and, in dual node mode, the remote one). Never run it.

## Known issues (not yet fixed)
- None currently.

## Not yet verified on a Pi
The config file, single/dual node mode and shared camera setup (`camera_setup.py`) were written and reviewed on Windows but not run on the Pis. Confirm them on a Pi before relying on them, and update this section when done.
