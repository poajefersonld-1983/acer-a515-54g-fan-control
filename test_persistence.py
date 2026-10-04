"""Persistent profiles must round-trip and reject untested commands/values."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("daemon", Path(__file__).resolve().parent / "daemon.py")
daemon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daemon)


class Profiles(unittest.TestCase):
    def test_saved_mode_survives_reloading(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            self.assertEqual(daemon.read_profile(path), ("auto", None))
            for mode, pwm in (("manual", 217), ("max", 255), ("auto", None)):
                daemon.save_profile(mode, pwm, path)
                self.assertEqual(daemon.read_profile(path), (mode, pwm))
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertFalse(path.with_suffix(".tmp").exists())

    def test_invalid_save_preserves_previous_choice(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            daemon.save_profile("manual", 217, path)
            for mode, pwm in (("manual", 0), ("manual", 256), ("quit", None), ("write_ec", 3)):
                with self.subTest(mode=mode, pwm=pwm), self.assertRaises(ValueError):
                    daemon.save_profile(mode, pwm, path)
                self.assertEqual(daemon.read_profile(path), ("manual", 217))


if __name__ == "__main__":
    unittest.main()
