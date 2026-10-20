import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import outcomes  # noqa: E402


def spawn_line(tid, prompt, model=None, ts="2026-09-30T10:00:00Z"):
    inp = {"description": "d", "prompt": prompt, **({"model": model} if model else {})}
    return {"type": "assistant", "timestamp": ts,
            "message": {"model": "claude-opus-5-5", "content": [{"type": "tool_use", "id": tid, "name": "Agent", "input": inp}]}}


def launched(tid, resolved):
    return {"type": "user", "toolUseResult": {"isAsync": True, "status": "async_launched", "resolvedModel": resolved},
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": "Async agent launched"}]}]}}


def notify(tid, status, result="done"):
    return {"type": "user", "message": {"content": f"<task-notification> <task-id>a1</task-id> <tool-use-id>{tid}</tool-use-id> "
                                                   f"<status>{status}</status> <summary>s</summary> <result>{result}</result> </task-notification>"}}


class OutcomeTests(unittest.TestCase):
    def session(self, lines):
        tmp = tempfile.mkdtemp()
        path = Path(tmp) / "s.jsonl"
        path.write_text("\n".join(json.dumps(l) for l in lines), encoding="utf-8")
        return outcomes.propose(outcomes.scan(path))

    def test_outcomes(self):
        props = self.session([
            spawn_line("t1", "Implement W4-P3 Plan risk in ArenaPy", "sonnet"), launched("t1", "claude-sonnet-5"),
            notify("t1", "completed"),
            spawn_line("t2", "Implement W4-P4 CP-SAT proposer", "opus"), launched("t2", "claude-opus-5-5"),
            notify("t2", "failed"),
            spawn_line("t3", "Final review of block 6D-W4 in ArenaPy", "fable"), launched("t3", "claude-fable-5-1"),
            notify("t3", "completed"),
            spawn_line("t4", "Fix the confirmed findings of the 6D-W4 final review", "opus"), launched("t4", "claude-opus-5-5"),
            notify("t4", "completed", "Status: BLOCKED on a missing fixture"),
            spawn_line("t5", "Implement W4-P3 Plan risk. A previous attempt stopped early.", "opus"),
            launched("t5", "claude-opus-5-5"), notify("t5", "completed"),
            spawn_line("t6", "Count the test files and reply with the number"),   # no model: inherit
            launched("t6", "claude-opus-5-5"),                                     # never reported
        ])
        got = {p["id"]: (p["tier"], p["outcome"], p["doubtful"]) for p in props}
        self.assertEqual(got["t1"], ("sonnet", "failed", False))      # redone by t5 (shared id + phrase)
        self.assertEqual(got["t2"], ("opus", "failed", False))        # status failed
        self.assertEqual(got["t3"], ("fable", "succeeded", False))    # a fix spawn doesn't fail the review
        self.assertEqual(got["t4"], ("opus", "failed", True))         # report says blocked: doubtful
        self.assertEqual(got["t5"], ("opus", "succeeded", False))
        self.assertNotIn("t6", got)                                    # no result yet: no proposal

    def test_same_role_respawn_is_doubtful(self):
        props = self.session([
            spawn_line("a", "Implement U1 group A of the plan", "opus"), launched("a", "claude-opus-5-5"), notify("a", "completed"),
            spawn_line("b", "Implement U1 group A of the plan again", "opus"), launched("b", "claude-opus-5-5"), notify("b", "completed"),
        ])
        self.assertEqual({p["id"]: (p["outcome"], p["doubtful"]) for p in props}, {"a": ("failed", True), "b": ("succeeded", False)})

    def test_blocked_needs_the_status_token(self):
        # "BLOCKED" is a status token; ordinary prose about a blocked port is a normal report
        props = self.session([spawn_line("p", "Implement W9-X2", "sonnet"), launched("p", "claude-sonnet-5"),
                              notify("p", "completed", "The port was blocked, so I used 8081. All tests pass.")])
        self.assertEqual([p["outcome"] for p in props], ["succeeded"])

    def test_two_notifications_in_one_message(self):
        # the first carries no <result>: its status must not be lost to the second one's
        text = ("<task-notification> <tool-use-id>x</tool-use-id> <status>failed</status> </task-notification>"
                "<task-notification> <tool-use-id>y</tool-use-id> <status>completed</status> <result>ok</result> </task-notification>")
        props = self.session([spawn_line("x", "Implement W9-X3", "sonnet"), launched("x", "claude-sonnet-5"),
                              spawn_line("y", "Implement W9-X4", "sonnet"), launched("y", "claude-sonnet-5"),
                              {"type": "user", "message": {"content": text}}])
        self.assertEqual({p["id"]: p["outcome"] for p in props}, {"x": "failed", "y": "succeeded"})

    def test_apply_refreshes_auto_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "routing.jsonl"
            log.write_text(json.dumps({"source": "agent", "tool_use_id": "t1", "prompt": "x", "outcome": "succeeded",
                                       "outcome_source": "auto"}) + "\n", encoding="utf-8")
            props = [{"id": "t1", "brief": "x", "tier": "opus", "outcome": "failed", "reason": "status failed", "doubtful": False}]
            self.assertEqual(outcomes.apply(log, props), 1)
            self.assertEqual(json.loads(log.read_text(encoding="utf-8"))["outcome"], "failed")

    def test_queued_notification_attachment(self):
        # a notification that lands while the orchestrator is busy is recorded as a queued_command attachment
        queued = {"type": "attachment", "attachment": {"type": "queued_command", "prompt": notify("q", "failed")["message"]["content"]}}
        props = self.session([spawn_line("q", "Implement W9-X1", "sonnet"), launched("q", "claude-sonnet-5"), queued])
        self.assertEqual([(p["id"], p["outcome"]) for p in props], [("q", "failed")])

    def test_sibling_milestones_are_not_redos(self):
        # one wave: different milestones of block 6D-W3, each brief mentioning the block and a sibling
        props = self.session([
            spawn_line("m1", "Implement milestone W3-M1 Energy per state (block 6D-W3; W3-M3 comes next)", "sonnet"),
            launched("m1", "claude-sonnet-5"), notify("m1", "completed"),
            spawn_line("m3", "Implement milestone W3-M3 Workers (block 6D-W3, after W3-M1)", "opus"),
            launched("m3", "claude-opus-5-5"), notify("m3", "completed"),
        ])
        self.assertEqual({p["id"]: p["outcome"] for p in props}, {"m1": "succeeded", "m3": "succeeded"})

    def test_apply_leaves_ambiguous_briefs_alone(self):
        # the same brief spawned twice (a redo): brief matching can't tell the entries apart, so neither is guessed
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "routing.jsonl"
            log.write_text("\n".join(json.dumps({"source": "agent", "prompt": "Implement W4-P3", "label": None})
                                     for _ in range(2)) + "\n", encoding="utf-8")
            props = [{"id": "a", "brief": "Implement W4-P3", "tier": "sonnet", "outcome": "failed", "reason": "r", "doubtful": True},
                     {"id": "b", "brief": "Implement W4-P3", "tier": "sonnet", "outcome": "succeeded", "reason": "r", "doubtful": False}]
            self.assertEqual(outcomes.apply(log, props), 0)

    def test_apply_matches_by_id_then_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "routing.jsonl"
            rows = [{"source": "agent", "tool_use_id": "t1", "prompt": "x", "label": None},
                    {"source": "agent", "prompt": "Implement W4-P4", "label": None},
                    {"source": "agent", "prompt": "done already", "outcome": "succeeded", "outcome_source": "user"},
                    {"prompt": "a user prompt", "label": None}]
            log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            props = [{"id": "t1", "brief": "y", "tier": "sonnet", "outcome": "failed", "reason": "r", "doubtful": False},
                     {"id": "t9", "brief": "Implement W4-P4", "tier": "opus", "outcome": "succeeded", "reason": "r", "doubtful": True},
                     {"id": "t8", "brief": "done already", "tier": "opus", "outcome": "failed", "reason": "r", "doubtful": False}]
            self.assertEqual(outcomes.apply(log, props), 2)
            out = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual((out[0]["outcome"], out[0]["outcome_tier"], out[0]["outcome_source"]), ("failed", "sonnet", "auto"))
        self.assertEqual((out[1]["outcome"], out[1]["outcome_doubtful"]), ("succeeded", True))
        self.assertEqual(out[2]["outcome_source"], "user")   # a confirmed outcome is never overwritten
        self.assertNotIn("outcome", out[3])


if __name__ == "__main__":
    unittest.main()
