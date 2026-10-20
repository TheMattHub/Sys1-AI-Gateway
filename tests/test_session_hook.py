import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fake_laya

REPO = Path(__file__).resolve().parents[1]


class SessionHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = fake_laya.start()
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def run_hook(self, config_text: str, paused: bool = False) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text(config_text, encoding="utf-8")
            if paused:
                (Path(tmp) / "paused").touch()
            proc = subprocess.run([sys.executable, "-m", "system1_gateway.session_hook"], capture_output=True,
                                  text=True, encoding="utf-8", timeout=30, cwd=tmp,
                                  env={**os.environ, "PYTHONPATH": str(REPO), "SYSTEM1_CONFIG": str(config),
                                       "SYSTEM1_INSTALL_DIR": str(Path(config).parent)})  # not the real pause file
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)["systemMessage"] if proc.stdout else ""

    def test_silent_when_routing_off_or_healthy(self):
        self.assertEqual(self.run_hook('[gateway]\nprovider = "laya"\n'), "")  # routing off: no health probe
        self.assertEqual(self.run_hook(f'[routing]\nenabled = true\n[providers.laya]\nendpoint = "{self.endpoint}"\n'), "")

    def test_engine_down_with_routing_on(self):
        text = self.run_hook('[routing]\nenabled = true\n[providers.laya]\nendpoint = "http://127.0.0.1:9"\n')
        self.assertIn("'laya' is down", text)
        self.assertIn("start.ps1", text)

    def test_silent_when_paused(self):
        # a deliberate /system1:toggle off must not be reported as a down engine at every session start
        self.assertEqual(self.run_hook('[routing]\nenabled = true\n[providers.laya]\nendpoint = "http://127.0.0.1:9"\n',
                                       paused=True), "")

    def test_feature_labels_count_as_labeled(self):
        from system1_gateway.session_hook import unlabeled_count
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "routing.jsonl"
            log.write_text("\n".join(json.dumps(r) for r in (
                {"prompt": "a", "label": None}, {"prompt": "b", "label": None, "feature_labels": {"review": "yes"}})),
                encoding="utf-8")
            self.assertEqual(unlabeled_count(str(log)), 1)

    def test_calibration_reminder(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "routing.jsonl"
            rows = ([{"prompt": f"p{i}", "label": None} for i in range(30)] + [{"prompt": "x", "label": "opus"}]
                    + [{"prompt": "s", "source": "skill", "label": None}])  # skill picks aren't routing labels
            log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            def config(log_dirs: str) -> str:
                return (f'[routing]\nenabled = true\nlog_dirs = {log_dirs}\nlog_file = "{log.as_posix()}"\n'
                        f'[providers.laya]\nendpoint = "{self.endpoint}"\n')
            self.assertIn("30 routing prompts", self.run_hook(config('["~"]')))
            self.assertEqual(self.run_hook(config("[]")), "")  # logging off: no reminder
            log.write_text("\n".join(json.dumps(r) for r in rows[1:]), encoding="utf-8")  # 29 unlabeled
            self.assertEqual(self.run_hook(config('["~"]')), "")

    def test_config_errors(self):
        self.assertIn("config error", self.run_hook("not = [toml"))
        self.assertIn("config error", self.run_hook('[routing]\nenabled = true\n[gateway]\nprovider = "nope"\n'))


if __name__ == "__main__":
    unittest.main()
