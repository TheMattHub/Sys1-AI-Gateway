import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from system1_gateway import calibration
from system1_gateway.config import Config
from system1_gateway.gateway import Gateway

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import calibrate  # noqa: E402

Q = {"question": "Ship the release today?", "options": ["ship", "hold"]}


def gateway(entries, **mock):
    return Gateway(Config(provider="mock", providers={"mock": mock}), calibration=entries)


def overconfident_samples(n=300, seed=1):
    """70% accurate, but the model always claims ~95%."""
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        right = rnd.random() < 0.7
        top, other = ("a", "b") if right else ("b", "a")
        p = 0.9 + 0.09 * rnd.random()
        out.append(({top: p, other: 1 - p}, "a"))
    return out


class ScaleAndLookupTests(unittest.TestCase):
    def test_scale_keeps_argmax_and_softens(self):
        q = calibration.scale({"a": 0.9, "b": 0.1}, 3.0)
        self.assertAlmostEqual(sum(q.values()), 1.0)
        self.assertTrue(0.5 < q["a"] < 0.9)
        self.assertAlmostEqual(calibration.scale({"a": 0.9, "b": 0.1}, 1.0)["a"], 0.9)

    def test_find_prefers_question_then_option_count_and_matches_model(self):
        entries = [{"provider": "laya", "model": "m", "question": None, "n_options": 2, "temperature": 2.0},
                   {"provider": "laya", "model": "m", "question": "q1", "n_options": 2, "temperature": 3.0},
                   {"provider": "laya", "model": "other", "question": None, "n_options": 3, "temperature": 9.0}]
        self.assertEqual(calibration.find(entries, "laya", "m", "q1", 2)["temperature"], 3.0)
        self.assertEqual(calibration.find(entries, "laya", "m", "q2", 2)["temperature"], 2.0)
        self.assertIsNone(calibration.find(entries, "laya", "m", "q1", 3))
        self.assertIsNone(calibration.find(entries, "laya", "m2", "q1", 2))  # stale fit for another checkpoint

    def test_load_skips_bad_files_and_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp) / "a.json", Path(tmp) / "b.json"
            good.write_text(json.dumps({"entries": [{"temperature": 2}, {"temperature": 0}, {"temperature": "x"}]}))
            bad.write_text("not json")
            self.assertEqual(len(calibration.load((good, bad, Path(tmp) / "missing.json"))), 1)


class GatewayCalibrationTests(unittest.TestCase):
    PROBS = {"ship": 0.9, "hold": 0.1}

    def test_applied_before_threshold(self):
        entry = {"provider": "mock", "model": None, "question": None, "n_options": 2, "temperature": 6.0}
        raw = {"decision": "ship", "confidence": 0.9, "probabilities": self.PROBS}
        r = gateway([], response=raw).decide(Q)
        self.assertEqual((r["status"], r["calibrated"], r["confidence"]), ("decided", False, 0.9))
        r = gateway([entry], response=raw).decide(Q)  # at T=6 the claimed 0.90 is really 0.59
        self.assertEqual((r["status"], r["calibrated"]), ("abstained", True))
        self.assertAlmostEqual(r["confidence"], 0.59, places=2)
        self.assertAlmostEqual(sum(r["probabilities"].values()), 1.0, places=3)

    def test_bad_probabilities_are_malformed(self):
        for probs in ({"ship": 0.9}, {"ship": 1.5, "hold": 0.1}, {"ship": 0.9, "maybe": 0.1}, "high"):
            with self.subTest(probs=probs):
                r = gateway([], response={"decision": "ship", "confidence": 0.9, "probabilities": probs}).decide(Q)
                self.assertEqual(r["error"]["code"], "malformed_response")


class FitTests(unittest.TestCase):
    def test_fit_softens_overconfidence(self):
        samples = overconfident_samples()
        t = calibrate.fit_temperature(samples)
        self.assertGreater(t, 1.5)
        before, after = calibrate.metrics(samples, 1.0, 0.8), calibrate.metrics(samples, t, 0.8)
        self.assertEqual(before["accuracy"], after["accuracy"])  # temperature never changes the argmax
        self.assertLess(after["ece"], before["ece"] / 2)
        self.assertLess(after["nll"], before["nll"])

    def test_feature_requests(self):
        items = calibrate.feature_requests({"prompt": "Review the diff", "feature_labels": {"review": "yes", "design": "no", "bogus": "yes", "read_only": "maybe"}})
        self.assertEqual(sorted(label for _, label in items), ["no", "yes"])
        self.assertTrue(all(req["options"] == ["yes", "no"] for req, _ in items))
        self.assertEqual(calibrate.feature_requests({"prompt": "x"}), [])
        self.assertEqual(calibrate.feature_requests({"prompt": "x", "source": "skill", "feature_labels": {"review": "yes"}}), [])

    def test_to_request(self):
        req, label = calibrate.to_request({"prompt": "Rename x to y in utils.py", "label": "Haiku"})
        self.assertTrue(label.startswith("haiku:"))
        self.assertEqual(req["min_confidence"], 0.0)
        self.assertEqual(calibrate.to_request({"question": "ok?", "label": "yes"})[1], "yes")
        for entry in ({"prompt": "x", "label": None}, {"prompt": "x", "label": "fable"}, {"other": 1},
                      {"prompt": "x", "source": "skill", "label": "opus"}):  # skill picks are calibrated separately
            self.assertIsNone(calibrate.to_request(entry))

    def test_end_to_end_with_mock_writes_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, data, out = Path(tmp) / "c.toml", Path(tmp) / "d.jsonl", Path(tmp) / "home"
            config.write_text('[gateway]\nprovider = "mock"\n', encoding="utf-8")
            # mock always picks the first option: haiku. Label half of them opus -> 50% accuracy.
            data.write_text("\n".join(json.dumps({"prompt": f"Task number {i} for the model", "label":
                                                  "haiku" if i % 2 else "opus"}) for i in range(12)), encoding="utf-8")
            env = {**os.environ, "SYSTEM1_CONFIG": str(config), "USERPROFILE": str(out), "HOME": str(out)}
            proc = subprocess.run([sys.executable, str(REPO / "scripts" / "calibrate.py"), str(data), "--json",
                                   "--write"], capture_output=True, text=True, encoding="utf-8", timeout=60, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            written = json.loads((out / ".system1-gateway" / "calibration.json").read_text(encoding="utf-8"))
        self.assertEqual(report["fits"][0]["after"]["accuracy"], 0.5)
        # One well-covered question: its own fit only, no fallback learned from it.
        self.assertEqual([e["question"] is None for e in written["entries"]], [False])
        self.assertEqual(written["entries"][0]["data"], "d.jsonl")


if __name__ == "__main__":
    unittest.main()
