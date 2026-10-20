"""usage_report.py against a synthetic Claude Code projects dir: turns, hints, spawns, subagent costs."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HINT = ("System-1 routing hint (laya, confidence {c}): suggested model tier for this task is **{t}**. "
        "When you spawn subagents for it, prefer model=\"{t}\" unless ...")


def line(**d):
    return json.dumps(d)


def prompt(t):
    return line(type="user", timestamp=t, origin={"kind": "human"},
                message={"role": "user", "content": [{"type": "text", "text": "secret prompt text"}]})


def hint(t, tier, c=0.8):
    return line(type="attachment", timestamp=t, attachment={"type": "hook_additional_context",
                                                            "content": [HINT.format(c=c, t=tier)]})


def spawn(t, tool_id, model=None):
    inp = {"description": "x", "prompt": "secret task text", **({"model": model} if model else {})}
    return line(type="assistant", timestamp=t, message={"role": "assistant", "model": "claude-opus-5-5",
                                                         "content": [{"type": "tool_use", "id": tool_id,
                                                                      "name": "Agent", "input": inp}]})


def write_subagent(session_dir: Path, tool_id: str, model: str, output_tokens: int):
    sub = session_dir / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / f"agent-{tool_id}.meta.json").write_text(json.dumps({"toolUseId": tool_id}))
    (sub / f"agent-{tool_id}.jsonl").write_text(line(
        type="assistant", message={"model": model, "usage": {"input_tokens": 0, "output_tokens": output_tokens}}))


class UsageReportTests(unittest.TestCase):
    def test_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "c--src-demo"
            proj.mkdir(parents=True)
            session = proj / "s1.jsonl"
            session.write_text("\n".join([
                prompt("2026-09-24T10:00:00Z"), hint("2026-09-24T10:00:01Z", "sonnet"),
                spawn("2026-09-24T10:00:10Z", "t1", "sonnet"),            # followed
                prompt("2026-09-24T10:05:00Z"), hint("2026-09-24T10:05:01Z", "sonnet"),
                spawn("2026-09-24T10:05:10Z", "t2", "opus"),              # upgraded
                prompt("2026-09-24T10:10:00Z"),
                spawn("2026-09-24T10:10:10Z", "t3", "opus"),              # baseline (no hint)
                spawn("2026-09-24T10:10:20Z", "t4", "sonnet"),            # baseline
            ]), encoding="utf-8")
            for tid, model in (("t1", "claude-sonnet-5"), ("t2", "claude-opus-5-5"), ("t3", "claude-opus-5-5"),
                               ("t4", "claude-sonnet-5")):
                write_subagent(proj / "s1", tid, model, 1_000_000)  # 1M output tokens each
            env = {**os.environ, "SYSTEM1_CONFIG": str(Path(tmp) / "none.toml")}
            Path(env["SYSTEM1_CONFIG"]).write_text('[gateway]\nprovider = "mock"\n', encoding="utf-8")
            proc = subprocess.run([sys.executable, str(REPO / "scripts" / "usage_report.py"), "--json",
                                   "--projects-dir", str(Path(tmp) / "projects"), "--days", "36500"],
                                  capture_output=True, text=True, encoding="utf-8", timeout=60, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("secret", proc.stdout)  # aggregates only
        r = json.loads(proc.stdout)
        self.assertEqual(r["spawns"]["outcomes"], {"followed": 1, "upgraded": 1, "baseline": 2})
        self.assertEqual(r["spawns"]["adherence"], 0.5)
        self.assertEqual(r["reach"]["hints"], 2)
        self.assertEqual(r["reach"]["prompts"], 3)
        # Output prices: opus-5-5 $20, sonnet-5 $10 per 1M. Baseline mix 50/50 -> $15 expected; followed sonnet
        # spawn cost $10, so $5 saved. The upgraded spawn cost $20 vs $10 at the hinted sonnet: $10 missed.
        self.assertEqual((r["cost_usd"]["realised_savings"], r["cost_usd"]["missed_savings"]), (5.0, 10.0))
        self.assertEqual(r["cost_usd"]["total_subagents"], 60.0)
        self.assertEqual([o["hint"] + ">" + o["spawned"] for o in r["spawns"]["overrides"]], ["sonnet>opus"])


class ShadowStatsTests(unittest.TestCase):
    def test_shadow_stats(self):
        sys.path.insert(0, str(REPO / "scripts"))
        from usage_report import shadow_stats
        entries = [
            {"source": "agent", "decision": "haiku: quick", "chosen": "sonnet", "label": "haiku"},  # cheaper, right
            {"source": "agent", "decision": "opus: complex", "chosen": "opus", "label": None},      # agrees
            {"source": "agent", "decision": "sonnet: well", "chosen": "inherit", "label": "opus"},  # cheaper, wrong
            {"source": "agent", "decision": None, "chosen": "opus", "label": "skip"},               # abstained
            {"decision": "haiku: quick", "label": "haiku"},                                         # a user prompt
        ]
        self.assertEqual(shadow_stats(entries), {"spawns": 3, "agree": 0.333, "system1_cheaper": 2,
                                                 "labeled": 2, "accuracy_on_labeled": 0.5})


if __name__ == "__main__":
    unittest.main()
