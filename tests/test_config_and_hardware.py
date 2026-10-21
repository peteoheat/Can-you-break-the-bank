import os
import tempfile
import unittest

from app_config import load_config
from hardware import SimulatedHardware, create_hardware


class ConfigTests(unittest.TestCase):
    def write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False)
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_defaults(self):
        config = load_config(self.write(""))
        self.assertEqual(config["app_mode"], "vault")
        self.assertEqual(config["hardware_backend"], "auto")
        self.assertTrue(config["fullscreen"])

    def test_values(self):
        config = load_config(self.write("[app]\nmode = enrol\nfullscreen = false\n[hardware]\nbackend = simulated\n"))
        self.assertEqual(config["app_mode"], "enrol")
        self.assertFalse(config["fullscreen"])
        self.assertEqual(config["hardware_backend"], "simulated")

    def test_bad_values_rejected(self):
        with self.assertRaises(ValueError):
            load_config(self.write("[app]\nmode = nonsense\n"))
        with self.assertRaises(ValueError):
            load_config(self.write("[hardware]\nbackend = nonsense\n"))


class HardwareTests(unittest.TestCase):
    def test_simulated_backend(self):
        hardware = create_hardware({"hardware_backend": "simulated"})
        self.assertIsInstance(hardware, SimulatedHardware)
        hardware.beep()
        hardware.lights((0, 255, 0))
        hardware.show_text("hello")
        hardware.close()

    def test_auto_falls_back_when_pi_libraries_are_missing(self):
        # RPi.GPIO can't be imported on a development machine
        try:
            import RPi.GPIO  # noqa: F401
            self.skipTest("running on a Pi")
        except ImportError:
            pass
        self.assertIsInstance(create_hardware({"hardware_backend": "auto"}), SimulatedHardware)


if __name__ == "__main__":
    unittest.main()
