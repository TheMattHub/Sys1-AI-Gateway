import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import evaluate  # noqa: E402


class ScoreTests(unittest.TestCase):
    def test_auroc(self):
        self.assertEqual(evaluate.auroc([(0.9, True), (0.1, False)]), 1.0)
        self.assertIsNone(evaluate.auroc([(0.9, True)]))

    def test_feature_scores(self):
        rows = [("yes", 0.9, "yes"), ("no", 0.8, "yes"), (None, None, "no"), ("no", 0.95, "no")]
        s = evaluate.feature_scores(rows, threshold=0.85)
        self.assertEqual((s["n"], s["accuracy"]), (4, 0.5))
        self.assertEqual((s["coverage_at_threshold"], s["accuracy_at_threshold"]), (0.5, 1.0))

    def test_rule_scores(self):
        rows = [("opus", "failed", "sonnet"), ("sonnet", "failed", "sonnet"), (None, "failed", "haiku"),
                ("haiku", "succeeded", "sonnet"), ("sonnet", "succeeded", "sonnet"), ("opus", "succeeded", "sonnet")]
        s = evaluate.rule_scores(rows)
        self.assertEqual((s["failed"], s["safety"]), (3, 1 / 3))       # only opus > sonnet is safe
        self.assertEqual((s["succeeded"], s["agreement"], s["savings"]), (3, 2 / 3, 1 / 3))

    def test_verdict(self):
        bars = {"min_feature_accuracy": 0.85, "min_safety": 0.95, "min_failures": 2}
        good = {k: {"accuracy_at_threshold": 0.9} for k in ("read_only", "design", "review", "specified")}
        ok, why = evaluate.verdict(good, {"failed": 3, "safety": 1.0}, bars)
        self.assertTrue(ok)
        # a feature without labels is unmet, not skipped: READY needs every feature measured
        ok, why = evaluate.verdict({"review": {"accuracy_at_threshold": 0.99}}, {"failed": 3, "safety": 1.0}, bars)
        self.assertFalse(ok)
        self.assertTrue(any("design" in w for w in why))
        ok, why = evaluate.verdict({"read_only": {"accuracy_at_threshold": 0.7}}, {"failed": 1, "safety": None}, bars)
        self.assertFalse(ok)
        self.assertEqual(len(why), 6)  # read_only too low, 3 features unlabeled, too few failures, safety unknown


class MainTests(unittest.TestCase):
    def test_missing_log_is_a_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.toml"
            cfg.write_text('[gateway]\nprovider = "mock"\n', encoding="utf-8")
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"SYSTEM1_CONFIG": str(cfg), "SYSTEM1_INSTALL_DIR": tmp}), redirect_stdout(out):
                code = evaluate.main(["--log", str(Path(tmp) / "missing.jsonl")])
        self.assertEqual(code, 1)
        self.assertIn("cannot read", out.getvalue())

    def test_end_to_end_with_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "routing.jsonl"
            rows = [{"prompt": "Review the branch", "feature_labels": {"read_only": "yes", "design": "yes", "review": "yes", "specified": "yes"}},
                    {"source": "agent", "prompt": "Implement W1", "outcome": "failed", "outcome_tier": "sonnet"},
                    {"prompt": "no labels at all"}]
            log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            cfg = Path(tmp) / "config.toml"
            cfg.write_text('[gateway]\nprovider = "mock"\n', encoding="utf-8")
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"SYSTEM1_CONFIG": str(cfg), "SYSTEM1_INSTALL_DIR": tmp}), redirect_stdout(out):
                code = evaluate.main(["--log", str(log), "--json", "--min-failures", "1"])
            report = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report["n_entries"], 2)
        self.assertEqual(report["features"]["review"]["accuracy"], 1.0)     # mock says yes to everything
        self.assertEqual(report["rule_engine"]["safety"], 1.0)              # opus > sonnet
        self.assertTrue(report["ready"])


if __name__ == "__main__":
    unittest.main()
