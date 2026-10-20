import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import toggle  # noqa: E402

from system1_gateway.config import load_config  # noqa: E402
from system1_gateway.gateway import Gateway  # noqa: E402


class ToggleTests(unittest.TestCase):
    def run_toggle(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = toggle.main(list(argv))
        return code, out.getvalue()

    def test_off_on_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text('[gateway]\nprovider = "mock"\n[routing]\nenabled = true\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"SYSTEM1_CONFIG": str(config), "SYSTEM1_INSTALL_DIR": tmp}):
                self.assertEqual(self.run_toggle("off")[0], 0)
                self.assertTrue((Path(tmp) / "paused").exists())
                self.assertEqual(Gateway(load_config()).decide({"question": "q"})["status"], "abstained")
                self.assertIn("paused", self.run_toggle("status")[1])
                self.assertEqual(self.run_toggle("on")[0], 0)
                self.assertFalse((Path(tmp) / "paused").exists())
                code, out = self.run_toggle("status")
                self.assertIn("active", out)
                self.assertIn("routing: on", out)

    def test_on_warns_when_nothing_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text('[gateway]\nprovider = "mock"\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"SYSTEM1_CONFIG": str(config), "SYSTEM1_INSTALL_DIR": tmp}):
                self.assertIn("/system1:setup", self.run_toggle("on")[1])


if __name__ == "__main__":
    unittest.main()
