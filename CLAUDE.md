# CLAUDE.md

Raspberry Pi three-factor-auth vault game (RFID card, Wordle-style PIN, face recognition). See README.md for the overview.

## Environment
- Code runs on a Raspberry Pi (KDE, Python 3) from `/home/pi/PiFace/`; paths to videos, images and `includes/` are hard-coded to that location. Development happens on Windows, so the hardware modules (`RPi.GPIO`, `picamera2`, `neopixel_spi`, `board`, `dbus`, `smbus`) can't be imported or run here - review and edit only, don't try to execute the scripts.
- Each Pi drives an external HDMI screen (not a touchscreen); the Tkinter windows are fixed at 800x600 at the top-left (`+0+0`).
- No tests, build step or package manifest.
- `Images/` is tracked in git (all copyright material has been removed). `Fonts/` and `includes/` are git-ignored (mixed licensing, deal with later) - don't add or commit their contents. `includes/oled_091.py` is the smbus2 variant of the root `oled_091.py`.

## Deployment modes
The activity runs in one of two ways:
- **Single Pi:** alternate between `tk_add_user.py` (enrol users) and `tk_open_vault.py` (the game) on the same Pi, using its local Redis.
- **Two Pis:** normally enrolment runs on **PiFace1** (`192.168.8.152`) and the game on **PiFace2** (`192.168.8.153`). `redis-sync.py` replicates Redis between them and must stay **bi-directional**, so either Pi can do either job - e.g. PiFace1 can run the game when the enrolment queue is short but the game queue is long.

This is why two different Redis IP addresses appear in the scripts - they are the two Pis, not a mistake.

## Architecture
- `tk_open_vault.py`: Tkinter `AuthApp`. Factor 1 reads RFID from `/dev/ttyS0`; Factor 2 shells out to `secret-number.py <pin>` and treats a truthy exit code as a pass (exit 1 = success, 0 = failure - intentional, keep it); Factor 3 loops camera frames (the 10s timer starts on the first detected face; gives up after `face_wait_seconds` with no face) and passes early when `vote_required` of the last `vote_window` recognition passes matched (distance <= `match_threshold`), then holds the live video for `pass_hold_seconds` with a "PASSED" banner. The vote is 1:1 against the scanned card's enrolled encoding, so other faces in frame never affect it; boxes are green (this card), amber (another enrolled card) or red (not recognised). Detection/encoding runs on every 3rd frame (`recognise_every_n`), and each pass is one vote. Every pass is appended to `/home/pi/PiFace/face_log.csv` (git-ignored) for tuning the thresholds.
- `tk_add_user.py`: enrolment. Averages 10 face encodings and stores a hash at `card:<id>` (`name`, `pin`, pickled `encoding`) in local Redis.
- `redis-sync.py` replicates the local Redis to a second Pi via keyspace events; the other Redis scripts act on both local and remote.
- The camera, GPIO, NeoPixel and OLED are initialised at module import time, so importing these files has hardware side effects.

## Conventions
- The existing code is plain procedural/Tkinter style with 4-space indentation; match it. Some scripts (`delete_all_redis_keys.py`, `redis-sync.py`) use env vars for config, the others hard-code values.
- The remote Redis IP differs between scripts (`.152` vs `.153`) because each script is configured for the *other* Pi in the two-Pi setup (see Deployment modes); don't unify them without asking. `redis-sync.py` runs as a systemd service on **both** Pis, each with `REMOTE_REDIS_HOST` set to the other Pi (the script's `.153` default is just a fallback), which is what makes the sync bi-directional. Don't change the sync design in a way that makes it one-directional. The sync service name is also inconsistent: `sync-redis.service` in `reset_all_redis.sh` vs `redis-sync.service` in `delete_all_redis_keys.py`.
- `delete_all_redis_keys.py` is destructive (flushes local and remote Redis). Never run it.

## Known issues (not yet fixed)
- None currently.
