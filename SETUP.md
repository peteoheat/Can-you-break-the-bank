# Setting up Can You Break the Bank on a new Raspberry Pi

This walks through setting up one Pi. For two Pis (dual node mode), do it on each Pi and
follow the "two Pis only" notes. See [README.md](README.md) for what the activity does.

The commands are for a fresh install of Raspberry Pi OS Bookworm (Debian 12, Python 3.11) with
KDE Plasma. Bookworm doesn't allow `pip install` into the system Python (PEP 668), so the pip
packages go in a virtual environment inside the clone. Adapt the commands if your OS differs.

## 1. Hardware and OS

1. Install Raspberry Pi OS with KDE Plasma. Connect the HDMI screen, camera, RFID HAT, OLED,
   NeoPixel strip and beacon relay (see the Hardware list in the README).
2. Enable the interfaces with `sudo raspi-config`: I2C, SPI, the hardware serial port (login
   shell off, serial hardware on) and the camera if your OS asks. Reboot.
3. Log in to the desktop session on the HDMI screen. The Tkinter windows and the wallpaper
   change (via D-Bus) need that session, so run the scripts from a terminal inside it.

## 2. Install the dependencies

### System packages (apt)

```
sudo apt update && sudo apt full-upgrade
sudo apt install git cmake python3-venv python3-opencv redis-server ffmpeg python3-picamera2 \
    python3-dbus python3-serial python3-numpy python3-pil python3-pil.imagetk python3-redis \
    python3-rpi.gpio python3-smbus
```

- `python3-opencv` provides OpenCV (`cv2`), used by `tk_open_vault.py`, `tk_add_user.py` and
  `camera_setup.py` for the camera frames, the on-screen video and the face boxes.
- `cmake` is needed to build dlib (below).
- `ffmpeg` provides `ffplay`, which plays the granted and denied videos.
- On a Pi 5, use `python3-rpi-lgpio` instead of `python3-rpi.gpio`.

### Python packages (virtual environment)

The venv must use `--system-site-packages` so it can see the apt packages above (`cv2`,
`picamera2`, `dbus`, `RPi.GPIO` and so on). It lives inside the clone, so do this after cloning
the repo in section 3:

```
cd ~/Can-you-break-the-bank
python3 -m venv --system-site-packages .venv
.venv/bin/pip install smbus2 adafruit-circuitpython-neopixel-spi face_recognition
```

- `face_recognition` pulls in **dlib**, which does the face detection and encodings and is
  compiled when you install it. This is slow on a Pi and needs plenty of memory. If the build
  is killed, add swap and try again.
- `smbus2` is needed because the `oled_091.py` in `includes/` is the smbus2 variant.
- Don't also install OpenCV from pip: it can overwrite the apt copy's files and break `import cv2`.
- Check everything imports (no output means success):
  ```
  .venv/bin/python -c "import cv2, dlib, face_recognition, smbus2, picamera2, dbus, RPi.GPIO"
  ```

**Run every script with `.venv/bin/python`** (for example `.venv/bin/python tk_add_user.py`).
The scripts' `#!/usr/bin/python3` lines use the system Python, which can't see the pip packages.

## 3. Get the code and assets

1. Clone the repo into your home directory. This creates `~/Can-you-break-the-bank`:
   ```
   cd ~
   git clone https://github.com/peteoheat/Can-you-break-the-bank.git
   cd Can-you-break-the-bank
   ```
   `Images/` comes with it. The scripts work out where they are installed, so the rest of this
   guide assumes the clone is at `~/Can-you-break-the-bank`. If you put it elsewhere, use that path
   instead.
2. Copy `includes/` from your existing Pi or backup. It is not in git (mixed licensing). It
   holds the SB Components RFID HAT files, which are only needed if that HAT is the one in use:
   - `oled_091.py` (provided by SB Components - don't modify it)
   - `SB.png`
   - `Fonts/`, which must be **inside** `includes/` because `oled_091.py` loads its font from
     the folder next to itself

   You end up with `~/Can-you-break-the-bank/includes/oled_091.py`, `includes/SB.png` and
   `includes/Fonts/GothamLight.ttf`.
3. Create the virtual environment and install the pip packages (see section 2).

## 4. Create the config file

```
mkdir -p ~/.config/can-you-break-the-bank
cp ~/Can-you-break-the-bank/can-you-break-the-bank.cfg.example ~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg
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
   sed -e "s|@USER@|$USER|g" -e "s|@INSTALL_DIR@|$HOME/Can-you-break-the-bank|g" \
       ~/Can-you-break-the-bank/redis-sync.service.template \
       | sudo tee /etc/systemd/system/redis-sync.service > /dev/null
   sudo systemctl daemon-reload
   sudo systemctl enable --now redis-sync.service
   ```
2. Watch it with `journalctl -u redis-sync -f`. It should report the initial sync and that it
   is listening for changes.
3. The unit runs as your user from the clone with the system `/usr/bin/python3`, not the
   venv, so it reads your `~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg`, and the
   `redis` Python package must be installed system-wide (the `python3-redis` apt package above
   does this).
4. If you move the clone or change the config, restart it with
   `sudo systemctl restart redis-sync.service`.
5. If it fails with `status=200/CHDIR`, the unit's paths don't match the clone: reinstall it
   with the `sed` command above, then `sudo systemctl daemon-reload` and
   `sudo systemctl reset-failed redis-sync.service`.

Skip this step on a single Pi. `redis-sync.py` exits when there is no `remote_host`.

## 7. Test the hardware piece by piece

Run these from a terminal in the Pi's desktop session, in the clone (`cd ~/Can-you-break-the-bank`). Use the
venv's Python, as in section 2:

- `.venv/bin/python read_rfid.py` checks the OLED, RFID reader and buzzer. Scan a card, then press
  Ctrl+C.
- `.venv/bin/python change_wallpaper.py` checks the KDE wallpaper change.
- `.venv/bin/python show_all_keys.py` checks Redis (both sides in dual node mode). It prints PINs and
  face encodings, so don't run it in front of students.

## 8. Enrol users and run the game

1. `.venv/bin/python tk_add_user.py` - scan a card, enter a name and PIN, and let it capture the
   training images.
2. Two Pis: confirm the new `card:<id>` key shows up on the other Pi too.
3. `.venv/bin/python tk_open_vault.py` - play through all three factors.
4. Every Factor 3 recognition pass is logged to `face_log.csv` in the clone (`~/Can-you-break-the-bank`). Use it to
   tune the `[face_recognition]` settings if people are wrongly rejected or accepted.

## 9. Setting up the second Pi by cloning the first (two Pis only)

Instead of repeating sections 1-8, you can clone the first Pi's SD card (for example with
Raspberry Pi Imager's or `dd`'s image of the card) and give the copy its own identity. The
clone keeps the same user name and clone path, so the `.venv` and the `redis-sync` unit keep
working. The steps below use PiFace1 (`192.168.8.152`) as the source and PiFace2
(`192.168.8.153`) as the clone; swap them if you clone the other way.

Do the steps on the clone **before** putting it on the network next to the original: if the
original has a static IP that the clone still holds, they will clash.

1. **Point the Redis sync at the other Pi.** The clone's config still has the *original's*
   `remote_host`, so it would sync with itself. Edit
   `~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg` on the clone and set
   `remote_host` in `[redis]` to the original Pi's IP (`192.168.8.152`), then
   `sudo systemctl restart redis-sync.service`.
2. **Hostname:**
   ```
   sudo hostnamectl set-hostname PiFace2
   sudo sed -i 's/PiFace1/PiFace2/g' /etc/hosts
   ```
3. **IP address.** Bookworm uses NetworkManager. List the profiles with `nmcli con show`, then
   for a static address:
   ```
   sudo nmcli con mod "<connection name>" ipv4.addresses 192.168.8.153/24
   sudo nmcli con up "<connection name>"
   ```
   If the router hands out addresses by reservation, update the reservation for the clone's MAC
   address instead.
4. **Regenerate identifiers the clone shares with the original**, then reboot:
   ```
   sudo rm /etc/ssh/ssh_host_* && sudo dpkg-reconfigure openssh-server
   sudo rm /etc/machine-id && sudo systemd-machine-id-setup
   ```
   Clear the old SSH host key entry on any machine you connect from (`ssh-keygen -R <ip>`).
5. **Tidy up:** delete the cloned `face_log.csv` so the log is the clone's own. Redis keeps the
   original's enrolled cards, which is fine because the first sync is two-way. If the clone is a
   different Pi model, check the GPIO package (a Pi 5 needs `python3-rpi-lgpio`).
6. **Check the sync both ways.** From each Pi, `redis-cli -h <other Pi's IP> ping` should reply
   `PONG`, and `journalctl -u redis-sync -f` should show the initial sync. Enrol a card on one
   Pi and confirm the `card:<id>` key appears on the other, then repeat the other way round.

## Warning

Don't run `delete_all_redis_keys.py` or `reset_all_redis.sh` unless you mean to wipe Redis. In
dual node mode they wipe both Pis.
