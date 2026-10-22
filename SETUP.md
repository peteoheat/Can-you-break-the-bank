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
3. Log in to the desktop session on the HDMI screen. The app opens its window on that session,
   so run it from a terminal inside it.

## 2. Install the dependencies

### System packages (apt)

```
sudo apt update && sudo apt full-upgrade
sudo apt install git cmake python3-venv python3-opencv redis-server python3-picamera2 \
    python3-serial python3-numpy python3-redis python3-rpi.gpio python3-smbus \
    python3-pyqt6 python3-pyqt6.qtmultimedia gstreamer1.0-libav gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-alsa
```

- `python3-opencv` provides OpenCV (`cv2`), used for the camera frames and the face boxes.
- `python3-pyqt6` and `python3-pyqt6.qtmultimedia` are the window toolkit and its video player.
  Install PyQt6 with apt, not pip. Bookworm's Qt 6.4 plays video through GStreamer, hence the
  `gstreamer1.0-*` packages for the granted/denied videos and their sound.
- `cmake` is needed to build dlib (below).
- On a Pi 5, use `python3-rpi-lgpio` instead of `python3-rpi.gpio`.
- You may see two GStreamer `CRITICAL` messages in the terminal when the app starts
  (`GST_IS_ELEMENT (element)` and `gst_alsa_device_new: assertion 'caps' failed`). They come from
  Qt probing the audio devices (probably an HDMI port with no screen on it) and don't affect the
  video or its sound.

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
  .venv/bin/python -c "import cv2, dlib, face_recognition, smbus2, picamera2, RPi.GPIO, PyQt6.QtMultimedia"
  ```

**Run every script with `.venv/bin/python`** (for example `.venv/bin/python vault_app.py`).
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
2. **Two Pis only:** each Pi's Redis must accept connections from the other, with protected mode
   left on. Redis (7 and later) refuses any connection from another machine while protected mode
   is on and the default user has no password, however `bind` is set. So the answer is a
   password, plus a `bind` that listens on the Pi's LAN address (the Raspberry Pi OS default
   `bind 127.0.0.1 -::1` only listens on the Pi itself). Pick one password and use the same one
   on both Pis. On each Pi, using that Pi's own address (PiFace1 `192.168.8.152`, PiFace2
   `192.168.8.153`; check yours with `hostname -I`), edit `/etc/redis/redis.conf`:
   ```
   sudo nano /etc/redis/redis.conf
   ```
   ```
   bind 127.0.0.1 -::1 192.168.8.152
   protected-mode yes
   requirepass your-password-here
   ```
   Keep the loopback addresses (the app and `redis-sync.py` use them to reach the local Redis)
   and don't use `0.0.0.0`, which clashes with the specific address and opens Redis to every
   network. Restart Redis:
   ```
   sudo systemctl restart redis-server
   ```
   Then put the same password in the `[redis]` section of the config file on **both** Pis
   (section 4), which the app, the sync and the Redis scripts all use:
   ```
   password = your-password-here
   ```
   Confirm from each Pi, using the *other* Pi's address. `REDISCLI_AUTH` gives `redis-cli` the
   password without putting it in the command line:
   ```
   REDISCLI_AUTH='your-password-here' redis-cli -h 192.168.8.153 ping     # run on PiFace1; expect PONG
   ```
   Without the password you get `NOAUTH Authentication required` (the connection is allowed,
   the password is wrong or missing). `DENIED Redis is running in protected mode` means
   `requirepass` isn't set on the Pi you are connecting to. Anything that talks to the local
   Redis (including `redis-cli` on that Pi) now needs the password too.
3. **Limit who can connect.** The password is sent unencrypted, so keep the Pis on a private
   network and allow port 6379 from the other Pi only. With `ufw` (`sudo apt install ufw`), on
   PiFace1 (use PiFace2's address on PiFace2), and allow SSH first so you don't lock yourself out:
   ```
   sudo ufw allow ssh
   sudo ufw allow from 192.168.8.153 to any port 6379 proto tcp
   sudo ufw enable
   ```
4. **Make Redis wait for the network at boot.** With `bind` set to the Pi's LAN address, Redis
   fails to start (`Cannot assign requested address` in `/var/log/redis/redis-server.log`) if
   it starts before the Pi has that address, which is common on Wi-Fi, and systemd then gives up
   after five quick retries. On each Pi:
   ```
   sudo systemctl edit redis-server
   ```
   ```
   [Unit]
   After=network-online.target
   Wants=network-online.target
   StartLimitIntervalSec=0

   [Service]
   RestartSec=5
   ```
   Then `sudo systemctl daemon-reload`. Also give each Pi a fixed address (a DHCP reservation on
   the router, or a static IP), because the `bind` line and the other Pi's `remote_host` both
   depend on it. If Redis is already stuck failed, run
   `sudo systemctl reset-failed redis-server` before starting it.

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
4. The unit waits for the network and the local Redis, and retries every 10 seconds without
   giving up. If you installed it from an older copy of the template, re-run the `sed` command
   above and `sudo systemctl daemon-reload`. A service stuck in `failed` after earlier errors
   needs `sudo systemctl reset-failed redis-sync` before it will start again.
5. If you move the clone or change the config, restart it with
   `sudo systemctl restart redis-sync.service`.
6. If it fails with `status=200/CHDIR`, the unit's paths don't match the clone: reinstall it
   with the `sed` command above, then `sudo systemctl daemon-reload` and
   `sudo systemctl reset-failed redis-sync.service`.

Skip this step on a single Pi. `redis-sync.py` exits when there is no `remote_host`.

## 7. Test the hardware piece by piece

Run these from a terminal in the Pi's desktop session, in the clone (`cd ~/Can-you-break-the-bank`). Use the
venv's Python, as in section 2:

- `.venv/bin/python read_rfid.py` checks the OLED, RFID reader and buzzer. Scan a card, then press
  Ctrl+C.
- `.venv/bin/python show_all_keys.py` checks Redis (both sides in dual node mode). It prints PINs and
  face encodings, so don't run it in front of students.

## 8. Enrol users and run the game

1. `.venv/bin/python vault_app.py --mode enrol` - scan a card, enter a name and PIN, and let it
   capture the training images. (Or start it normally and click **Enrol users**.)
2. Two Pis: confirm the new `card:<id>` key shows up on the other Pi too.
3. Click **Open the vault** (or run `.venv/bin/python vault_app.py`) and play through all three
   factors. To try it in a window rather than full screen, add `--windowed`.
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

## 10. Start the game automatically at boot (optional kiosk mode)

This makes the Pi power on straight into the full-screen app, with no keyboard needed.
`run_vault.sh` runs the app and restarts it a few seconds later if it crashes. An autostart entry
runs that script when the desktop session starts.

1. **Log in automatically.** The Pi has to start the desktop session by itself. With
   `sudo raspi-config`, choose System Options, then Boot / Auto Login, then Desktop Autologin. If
   your KDE install uses SDDM, create `/etc/sddm.conf.d/autologin.conf` instead (use your own user
   name; `plasma` is the Wayland session and `plasmax11` the X11 one):
   ```
   [Autologin]
   User=pi
   Session=plasma
   ```
2. **Install the autostart entry.** `can-you-break-the-bank.desktop.template` has an
   `@INSTALL_DIR@` placeholder because the `Exec` line needs an absolute path; this fills it in
   (adjust the path if you cloned somewhere else):
   ```
   mkdir -p ~/.config/autostart
   sed "s|@INSTALL_DIR@|$HOME/Can-you-break-the-bank|g" \
       ~/Can-you-break-the-bank/can-you-break-the-bank.desktop.template \
       > ~/.config/autostart/can-you-break-the-bank.desktop
   ```
3. **Stop the screen going blank or locking.** In KDE System Settings, turn off screen energy
   saving (Power Management) and automatic screen locking (Screen Locking), or the vault will go
   dark or ask for a password.
4. **Choose which mode each Pi starts in** with `mode` in the `[app]` section of its config file
   (for example `enrol` on PiFace1 and `vault` on PiFace2). The on-screen button still switches.
5. Reboot and check it comes up. Its output, including any errors, is in `vault_app.log` in the
   clone (emptied when it passes 1 MB).

Notes:

- On a Pi the app treats a missing Redis, camera or `face_recognition` as an error rather than
  quietly using a stand-in. It waits up to 30 seconds for Redis at start-up, and if something is
  still missing it exits and `run_vault.sh` tries again, so check `vault_app.log` if it never
  appears.
- The Exit button (which asks for the admin PIN if `admin_pin` is set) ends the app and the
  wrapper, leaving the desktop. Start it again with `~/Can-you-break-the-bank/run_vault.sh`.
- To turn the kiosk off, delete `~/.config/autostart/can-you-break-the-bank.desktop`.
- Do this on each Pi. If you cloned the first Pi's card (section 9), the autostart entry came
  with it, so only check the `[app] mode` in the clone's config.
- This hasn't been tested on a Pi yet.
