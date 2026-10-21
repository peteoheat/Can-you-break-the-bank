"""
rfid.py

Reads access cards on a background thread, so the UI never blocks on the serial port (the old
scripts called ser.read(12) on the UI thread).

The reader only delivers a card when it has been armed: arm() throws away anything already
waiting on the port and the next card read is passed to on_card once, then the reader disarms.
Cards presented while it is not armed are ignored.

on_card(card_id) is called on the reader's thread, so the UI must hand the result over to its own
thread (e.g. with a Qt signal) rather than touching widgets directly.

create_card_reader(config, hardware, on_card) gives a SerialCardReader on the Pi, or a
SimulatedCardReader (where inject() stands in for a card) when [hardware] backend is simulated, or
auto and the Pi hardware is not available.
"""

import logging
import threading

log = logging.getLogger("rfid")

CARD_LENGTH = 12  # characters sent by the reader per card


class CardReader:
    def __init__(self, on_card, beep=None):
        self.on_card = on_card
        self._beep = beep
        self._armed = threading.Event()

    def arm(self):
        """Wait for the next card, ignoring any read before now."""
        self._armed.set()

    def disarm(self):
        self._armed.clear()

    def start(self):
        pass

    def stop(self):
        pass

    def _deliver(self, card_id):
        """Pass a card on if armed, then disarm so it is only delivered once."""
        if not self._armed.is_set():
            log.info("card %s ignored (not armed)", card_id)
            return
        self._armed.clear()
        if self._beep is not None:
            self._beep()
        self.on_card(card_id)


class SimulatedCardReader(CardReader):
    def inject(self, card_id):
        """Pretend a card was scanned."""
        self._deliver(card_id)


class SerialCardReader(CardReader):
    def __init__(self, port, on_card, beep=None):
        super().__init__(on_card, beep)
        self.port = port
        self._flush = threading.Event()
        self._stop = threading.Event()
        self._thread = None

    def arm(self):
        # The thread owns the port, so ask it to drop what has built up before delivering again
        self._flush.set()
        super().arm()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self):
        import serial
        # A short timeout so stop() is noticed, and so a gap in the data marks the end of a card
        with serial.Serial(self.port, 9600, timeout=0.5) as ser:
            buffer = b""
            while not self._stop.is_set():
                data = ser.read(CARD_LENGTH - len(buffer))
                if self._flush.is_set():
                    self._flush.clear()
                    ser.reset_input_buffer()
                    buffer = b""
                    continue
                if not data:
                    buffer = b""  # a partial card followed by silence is noise
                    continue
                buffer += data
                if len(buffer) < CARD_LENGTH:
                    continue
                try:
                    card_id = buffer.decode("utf-8")
                except UnicodeDecodeError:
                    card_id = None
                buffer = b""
                if card_id is not None:
                    self._deliver(card_id)


def create_card_reader(config, hardware, on_card):
    """Return a card reader for the config; simulated if the hardware is."""
    from hardware import SimulatedHardware
    if isinstance(hardware, SimulatedHardware):
        return SimulatedCardReader(on_card, hardware.beep)
    return SerialCardReader(config["serial_port"], on_card, hardware.beep)
