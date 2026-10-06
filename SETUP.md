# Setting up Can You Break the Bank on a new Raspberry Pi

This walks through setting up one Pi. For two Pis (dual node mode), do it on each Pi and
follow the "two Pis only" notes. See [README.md](README.md) for what the activity does.

The commands were written for Raspberry Pi OS with KDE Plasma (Debian 11, Python 3.9). Adapt
them if your OS differs.

## 1. Hardware and OS

1. Install Raspberry Pi OS with KDE Plasma. Connect the HDMI screen, camera, RFID HAT, OLED,
   NeoPixel strip and beacon relay (see the Hardware list in the README).
2. Enable the interfaces with `sudo raspi-config`: I2C, SPI, the hardware serial port (login
   shell off, serial hardware on) and the camera if your OS asks. Reboot.
3. Log in to the desktop session on the HDMI screen. The Tkinter windows and the wallpaper
   change (via D-Bus) need that session, so run the scripts from a terminal inside it.

## 2. Install the dependencies

### Required: OpenCV (`cv2`) and dlib

The game cannot run without these two libraries:

- **OpenCV (`cv2`)** is used by `tk_open_vault.py`, `tk_add_user.py` and `camera_setup.py`
  for the camera frames, the on-screen video and the face boxes.
- **dlib** does the face detection and the face encodings. It is installed as a dependency of
  `face_recognition` and is compiled when you install it.

```
sudo apt install cmake python3-opencv
pip3 install face_recognition
```

- Install OpenCV from apt (`python3-opencv`) **or** from pip (`opencv-python`), not both.
- Building dlib on a Pi is slow (it can take a long time) and needs plenty of memory. If the
  build is killed, add swap and try again.
- Check both work before going further: `python3 -c "import cv2, dlib, face_recognition"`

### Other system packages (apt)

```
sudo apt install redis-server ffmpeg python3-picamera2 python3-dbus python3-serial \
    python3-numpy python3-pil python3-pil.imagetk python3-redis python3-rpi.gpio python3-smbus
```

`ffmpeg` provides `ffplay`, which plays the granted and denied videos.

### Other Python packages (pip)

```
pip3 install adafruit-circuitpython-neopixel-spi smbus2
```

`smbus2` is needed because the `oled_091.py` in `includes/` is the smbus2 variant.

## 3. Get the code and assets

1. Clone the repo into your home directory. This creates `~/can-you-break-the-bank`:
   ```
   cd ~
   git clone https://github.com/peteoheat/Can-you-break-the-bank.git
   cd can-you-break-the-bank
   ```
   `Images/` comes with it. The scripts work out where they are installed, so the rest of this
   guide assumes the clone is at `~/can-you-break-the-bank`. If you put it elsewhere, use that path
   instead.
2. Copy `includes/` from your existing Pi or backup. It is not in git (mixed licensing). It
   holds the SB Components RFID HAT files, which are only needed if that HAT is the one in use:
   - `oled_091.py` (provided by SB Components - don't modify it)
   - `SB.png`
   - `Fonts/`, which must be **inside** `includes/` because `oled_091.py` loads its font from
     the folder next to itself

   You end up with `~/can-you-break-the-bank/includes/oled_091.py`, `includes/SB.png` and
   `includes/Fonts/GothamLight.ttf`.

## 4. Create the config file

```
mkdir -p ~/.config/can-you-break-the-bank
cp ~/can-you-break-the-bank/can-you-break-the-bank.cfg.example ~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg
```

Edit `~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg`:

- **One Pi (single node mode):** leave `remote_host` in `[redis]` empty.
- **Two Pis (dual node mode):** set `remote_host` to the *other* Pi's IP address. PiFace1
  points at PiFace2 and PiFace2 points at PiFace1, so the two config files differ.
- **USB webcam:** set `type = webcam` (and `webcam_device` if it isn't `/dev/video0`) in
  `[camera]`.
- Create this file on every Pi. A Pi with no config file silently runs in single node mode,
  so the Redis sync stops.

Every setting is optional and defaults to the original value. The example file explains each
one.

## 5. Redis

1. Start Redis and enable it at boot:
   ```
   sudo systemctl enable --now redis-server
   ```
   `redis.service` in the repo is a reference copy of the unit file.
2. **Two Pis only:** each Pi's Redis must accept connections from the other. Check `bind` and
   `protected-mode` in `/etc/redis/redis.conf`, restart Redis, and confirm from each Pi with
   `redis-cli -h <other Pi's IP> ping`.
3. The sync has no password support, so keep the Pis on a private network.

## 6. Redis sync (two Pis only)

1. Install and start the service. `redis-sync.service.template` has `@USER@` and
   `@INSTALL_DIR@` placeholders, which this command fills in with your user name and the clone's
   location (adjust the path if you cloned somewhere else):
   ```
   sed -e "s|@USER@|$USER|g" -e "s|@INSTALL_DIR@|$HOME/can-you-break-the-bank|g" \
       ~/can-you-break-the-bank/redis-sync.service.template \
       | sudo tee /etc/systemd/system/redis-sync.service > /dev/null
   sudo systemctl daemon-reload
   sudo systemctl enable --now redis-sync.service
   ```
2. Watch it with `journalctl -u redis-sync -f`. It should report the initial sync and that it
   is listening for changes.
3. The unit runs as your user from the clone with `/usr/bin/python3`, so it reads your
   `~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg`, and the `redis` Python package
   must be installed system-wide (the `python3-redis` apt package above does this).
4. If you move the clone or change the config, restart it with
   `sudo systemctl restart redis-sync.service`.

Skip this step on a single Pi. `redis-sync.py` exits when there is no `remote_host`.

## 7. Test the hardware piece by piece

Run these from a terminal in the Pi's desktop session, in the clone (`cd ~/can-you-break-the-bank`):

- `python3 read_rfid.py` checks the OLED, RFID reader and buzzer. Scan a card, then press
  Ctrl+C.
- `python3 change_wallpaper.py` checks the KDE wallpaper change.
- `python3 show_all_keys.py` checks Redis (both sides in dual node mode). It prints PINs and
  face encodings, so don't run it in front of students.

## 8. Enrol users and run the game

1. `python3 tk_add_user.py` - scan a card, enter a name and PIN, and let it capture the
   training images.
2. Two Pis: confirm the new `card:<id>` key shows up on the other Pi too.
3. `python3 tk_open_vault.py` - play through all three factors.
4. Every Factor 3 recognition pass is logged to `face_log.csv` in the clone (`~/can-you-break-the-bank`). Use it to
   tune the `[face_recognition]` settings if people are wrongly rejected or accepted.

## Warning

Don't run `delete_all_redis_keys.py` or `reset_all_redis.sh` unless you mean to wipe Redis. In
dual node mode they wipe both Pis.
