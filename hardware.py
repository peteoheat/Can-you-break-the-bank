"""
hardware.py

The Pi hardware used by the vault: the buzzer and beacon (GPIO), the NeoPixel ring and the OLED on
the SB Components RFID HAT. The app only talks to the Hardware interface below, so it can run
without the hardware:

  - RealHardware drives the GPIO, NeoPixels and OLED (Raspberry Pi only).
  - SimulatedHardware just logs what would have happened (any machine, e.g. development on Windows).

create_hardware(config) picks one from [hardware] backend: real, simulated, or auto (real if the
Pi libraries import, otherwise simulated with a warning).

Importing this module has no hardware side effects; creating RealHardware initialises the GPIO,
NeoPixels and OLED.
"""

import logging
import sys
import threading
import time

log = logging.getLogger("hardware")

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
OFF = (0, 0, 0)


class Hardware:
    """The interface the app uses. This base class does nothing; see the two backends below."""

    def beep(self, seconds=0.1):
        """Sound the buzzer on the RFID HAT."""

    def beacon(self, on):
        """Switch the flashing beacon relay on or off."""

    def lights(self, colour):
        """Fill the NeoPixel ring with one colour (stops the attract mode first)."""

    def attract_start(self):
        """Start the red/green/blue chase on the ring."""

    def attract_stop(self):
        """Stop the chase and turn the ring off."""

    def show_text(self, text, font_size=14, cords=None, box=False):
        """Show a line of text on the OLED, optionally with a box drawn round the screen."""

    def show_logo(self):
        """Show the logo on the OLED."""

    def clear_display(self):
        """Blank the OLED."""

    def close(self):
        """Turn everything off."""


class SimulatedHardware(Hardware):
    def beep(self, seconds=0.1):
        log.info("beep")

    def beacon(self, on):
        log.info("beacon %s", "on" if on else "off")

    def lights(self, colour):
        log.info("lights %s", colour)

    def attract_start(self):
        log.info("attract mode on")

    def attract_stop(self):
        log.info("attract mode off")

    def show_text(self, text, font_size=14, cords=None, box=False):
        log.info("OLED: %s", text)

    def show_logo(self):
        log.info("OLED: logo")

    def clear_display(self):
        log.info("OLED: cleared")


class RealHardware(Hardware):
    def __init__(self, config):
        # Imported here so SimulatedHardware (and the tests) don't need the Pi libraries
        import RPi.GPIO as GPIO
        import board
        import neopixel_spi

        self._GPIO = GPIO
        self._buzzer = config["buzzer_pin"]
        self._beacon = config["beacon_pin"]
        self._pixel_count = config["neopixel_count"]
        self._logo = config["oled_logo"]

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self._buzzer, GPIO.OUT)
        GPIO.setup(self._beacon, GPIO.OUT)
        GPIO.output(self._beacon, GPIO.HIGH)  # the relay is active low, so HIGH = beacon off

        neopixel_spi.GRB = "GRB"
        self._pixels = neopixel_spi.NeoPixel_SPI(
            board.SPI(),
            self._pixel_count,
            bpp=3,
            brightness=config["neopixel_brightness"],
            auto_write=False,
            frequency=config["neopixel_frequency"],
            pixel_order="GRB",
            bit0=0b10000000)
        self._pixel_lock = threading.Lock()
        self._attract_stop = threading.Event()
        self._attract_thread = None

        # The OLED comes from the RFID HAT's files in includes/ (git-ignored). The game works without it.
        self._oled = None
        try:
            sys.path.append(config["includes_dir"])
            from oled_091 import SSD1306
            self._oled = SSD1306()
        except Exception as error:
            log.warning("OLED not available (%s) - carrying on without it", error)

    def beep(self, seconds=0.1):
        self._GPIO.output(self._buzzer, self._GPIO.HIGH)
        time.sleep(seconds)
        self._GPIO.output(self._buzzer, self._GPIO.LOW)

    def beacon(self, on):
        self._GPIO.output(self._beacon, self._GPIO.LOW if on else self._GPIO.HIGH)

    def lights(self, colour):
        self.attract_stop()
        self._fill(colour)

    def _fill(self, colour):
        with self._pixel_lock:
            self._pixels.fill(colour)
            self._pixels.show()

    def attract_start(self):
        self.attract_stop()
        self._attract_stop = threading.Event()
        self._attract_thread = threading.Thread(target=self._attract, args=(self._attract_stop,), daemon=True)
        self._attract_thread.start()

    def attract_stop(self):
        self._attract_stop.set()
        if self._attract_thread is not None:
            self._attract_thread.join()
            self._attract_thread = None
        self._fill(OFF)

    def _attract(self, stop):
        # One lap of the ring per colour per second, with a 10 pixel long trail
        delay = 1 / self._pixel_count
        while not stop.is_set():
            for colour in (RED, GREEN, BLUE):
                for i in range(-1, self._pixel_count - 1):
                    if stop.is_set():
                        return
                    with self._pixel_lock:
                        self._pixels[i + 1] = colour
                        self._pixels[i - 10] = OFF
                        self._pixels.show()
                    time.sleep(delay)

    def show_text(self, text, font_size=14, cords=None, box=False):
        if self._oled is None:
            return
        if cords is None:
            self._oled.PrintText(text, FontSize=font_size)
        else:
            self._oled.PrintText(text, cords=cords, FontSize=font_size)
        if box:
            self._oled.DrawRect()
        self._oled.ShowImage()

    def show_logo(self):
        if self._oled is None:
            return
        self._oled.NoDisplay()
        self._oled.DirImage(self._logo)
        self._oled.DrawRect()
        self._oled.ShowImage()

    def clear_display(self):
        if self._oled is not None:
            self._oled.NoDisplay()

    def close(self):
        self.attract_stop()
        self.beacon(False)
        self.clear_display()


def create_hardware(config):
    """Return the Hardware chosen by [hardware] backend in the config."""
    backend = config["hardware_backend"]
    if backend == "simulated":
        return SimulatedHardware()
    if backend == "real":
        return RealHardware(config)
    try:  # auto
        return RealHardware(config)
    except ImportError as error:
        log.warning("Pi hardware libraries not available (%s) - using simulated hardware", error)
        return SimulatedHardware()
