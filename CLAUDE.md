# CLAUDE.md

Raspberry Pi three-factor-auth vault game (RFID card, Wordle-style PIN, face recognition). See README.md for the overview.

## Environment
- Code runs on a Raspberry Pi (KDE, Python 3) from `/home/pi/PiFace/`; paths to videos, images and `includes/` are hard-coded to that location. Development happens on Windows, so the hardware modules (`RPi.GPIO`, `picamera2`, `neopixel_spi`, `board`, `dbus`, `smbus`) can't be imported or run here - review and edit only, don't try to execute the scripts.
- Each Pi drives an external HDMI screen (not a touchscreen); the Tkinter windows are fixed at 800x600 at the top-left (`+0+0`).
- No tests, build step or package manifest.
- `Images/`, `Fonts/` and `includes/` are git-ignored (mixed licensing, deal with later). Don't add or commit their contents. `includes/oled_091.py` is the smbus2 variant of the root `oled_091.py`.

## Deployment modes
The activity runs in one of two ways:
- **Single Pi:** alternate between `tk_add_user.py` (enrol users) and `tk_open_vault.py` (the game) on the same Pi, using its local Redis.
- **Two Pis:** normally enrolment runs on **PiFace1** (`192.168.8.152`) and the game on **PiFace2** (`192.168.8.153`). `redis-sync.py` replicates Redis between them and must stay **bi-directional**, so either Pi can do either job - e.g. PiFace1 can run the game when the enrolment queue is short but the game queue is long.

This is why two different Redis IP addresses appear in the scripts - they are the two Pis, not a mistake.

## Architecture
- `tk_open_vault.py`: Tkinter `AuthApp`. Factor 1 reads RFID from `/dev/ttyS0`; Factor 2 shells out to `secret-number.py <pin>` and treats a truthy exit code as a pass (exit 1 = success, 0 = failure - intentional, keep it); Factor 3 loops 10s of camera frames and passes if `recognised_count > 10`.
- `tk_add_user.py`: enrolment. Averages 10 face encodings and stores a hash at `card:<id>` (`name`, `pin`, pickled `encoding`) in local Redis.
- `redis-sync.py` replicates the local Redis to a second Pi via keyspace events; the other Redis scripts act on both local and remote.
- The camera, GPIO, NeoPixel and OLED are initialised at module import time, so importing these files has hardware side effects.

## Conventions
- The existing code is plain procedural/Tkinter style with 4-space indentation; match it. Some scripts (`delete_all_redis_keys.py`, `redis-sync.py`) use env vars for config, the others hard-code values.
- The remote Redis IP differs between scripts (`.152` vs `.153`) because each script is configured for the *other* Pi in the two-Pi setup (see Deployment modes); don't unify them without asking. `redis-sync.py` runs as a systemd service on **both** Pis, each with `REMOTE_REDIS_HOST` set to the other Pi (the script's `.153` default is just a fallback), which is what makes the sync bi-directional. Don't change the sync design in a way that makes it one-directional. The sync service name is also inconsistent: `sync-redis.service` in `reset_all_redis.sh` vs `redis-sync.service` in `delete_all_redis_keys.py`.
- `delete_all_redis_keys.py` is destructive (flushes local and remote Redis). Never run it.

## Known issues (not yet fixed)
- Attract-mode thread race in `reset_app` (old thread checks the replaced stop event and busy-loops).
- `secret-number.py` `update_guess_display` dedent bug hides earlier guesses; timer label starts as `01:00.000` but the limit is 45s.
- `recognised_count` multiplies by the number of faces (nested loop); `argmin` crashes with no enrolled users; colour order differs from enrolment (no BGR2RGB in `tk_open_vault.py`).
- `tk_add_user.py` checks `redis_client.exists(card_id)` without the `card:` prefix.
