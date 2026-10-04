"""Validate that GUI input cannot request untested fan values or arbitrary writes."""
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("fan_backend", Path(__file__).resolve().parent / "backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class CommandBounds(unittest.TestCase):
    def test_only_tested_manual_values(self):
        for pwm in (183, 208, 217, 232, 255):
            self.assertEqual(backend.decode_command(json.dumps({"action": "manual", "pwm": pwm})),
                             ("manual", pwm))

    def test_rejects_unsafe_or_mistyped_values(self):
        for pwm in (0, 1, 182, 256, -1, True, 255.0, "255", None):
            with self.subTest(pwm=pwm), self.assertRaises(ValueError):
                backend.decode_command(json.dumps({"action": "manual", "pwm": pwm}))

    def test_no_arbitrary_hardware_commands(self):
        for message in ({"action": "write_ec", "address": 0x10, "value": 3},
                        {"action": "stop"}, {}, [], "max"):
            with self.subTest(message=message), self.assertRaises(ValueError):
                backend.decode_command(json.dumps(message))

    def test_modes_and_heartbeat(self):
        for action in ("auto", "max", "quit", "ping"):
            self.assertEqual(backend.decode_command(json.dumps({"action": action})), (action, None))


if __name__ == "__main__":
    unittest.main()
