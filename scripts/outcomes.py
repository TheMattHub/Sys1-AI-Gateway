"""Propose an outcome for every Agent spawn from Claude Code transcripts, and record it in the routing log.

    python scripts/outcomes.py [--days 30] [--projects-dir ~/.claude/projects] [--apply] [--json]

An outcome answers "did the model that ran this spawn get the job done?" (spec 2026-09-30, section 4):
- failed: the tool result was an error; the task notification's status was failed or stopped; the report
  says the agent was blocked (doubtful); or a later spawn in the same session redid the same task. A redo is a
  shared task id (W4-P3, U1, Task 12) plus a redo phrase ("previous attempt", "retry"), or a same-role
  re-spawn of that id without one (doubtful). "Fix the findings" spawns follow a review and don't fail it.
- succeeded: none of the above. A spawn with no result yet gets no proposal.
The tier is the model that actually ran (toolUseResult.resolvedModel), which also resolves "inherit".
Prints counts and the doubtful proposals only, on this machine. --apply writes outcome, outcome_reason,
outcome_tier, outcome_source = "auto" and outcome_doubtful to agent entries of the routing log that have no
outcome or only an auto one (a user-confirmed outcome is never changed), matched by tool_use_id, else by the
brief's first 2000 characters when that brief is unique. /system1:calibrate then
asks the user about the doubtful ones and records the answers with outcome_source = "user".
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from system1_gateway.config import ConfigError, load_config  # noqa: E402

TIER_ORDER = ["haiku", "sonnet", "opus", "fable"]
# Status tokens are matched as written (prose like "the port was blocked" is a normal report); phrases in any case.
BLOCKED = re.compile(r"\b(?:BLOCKED|NEEDS_CONTEXT)\b|(?i:could(?: not|n't) (?:complete|finish)|\bgave up\b"
                     r"|unable to (?:complete|finish))")
REDO = re.compile(r"previous attempt|\bretry\b|\bre-?run\b|\bredo\b|stopped (?:early|before)", re.I)
TASK_ID = re.compile(r"\b(?:[A-Z]{1,3}\d{1,3}(?:[-.][A-Z]?\d{1,3})*|Tasks? \d+)\b")
NOTIFY = re.compile(r"<task-notification>(.*?)(?:</task-notification>|$)", re.S)  # one block per notification
FIELD = {k: re.compile(rf"<{k}>(.*?)</{k}>", re.S) for k in ("tool-use-id", "status")}
RESULT = re.compile(r"<result>(.*?)(?:</result>|$)", re.S)
HEAD = 600  # redo phrases sit at the top of a brief


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict) and isinstance(c.get("text"), str))
    return ""


def tier_of(model) -> str | None:
    m = str(model or "").lower()
    return next((t for t in TIER_ORDER if t in m or (t == "fable" and "mythos" in m)), None)


def primary(brief: str) -> str | None:
    """The task a brief is about: the first task id in its opening line. Briefs also mention their block
    (6D-W3) and sibling milestones, so comparing every id they contain would call a normal wave a redo."""
    m = TASK_ID.search(brief[:200].split("\n", 1)[0])
    return re.sub(r"^Tasks ", "Task ", m.group(0)) if m else None


def role(brief: str) -> str:
    return " ".join(re.findall(r"[a-z]+", brief.lower())[:3])


def scan(path: Path) -> list:
    """Agent spawns of one session transcript, in order, with what became of them."""
    spawns, by_id = [], {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        content, tur = msg.get("content"), d.get("toolUseResult")
        for c in content if isinstance(content, list) else []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and c.get("name") in ("Agent", "Task") and isinstance(c.get("input"), dict):
                s = {"id": c.get("id"), "ts": d.get("timestamp", ""), "brief": str(c["input"].get("prompt") or ""),
                     "model": c["input"].get("model") or "inherit", "main_model": msg.get("model"),
                     "is_error": False, "status": None, "report": ""}
                spawns.append(s)
                by_id[s["id"]] = s
            elif c.get("type") == "tool_result" and c.get("tool_use_id") in by_id:
                s = by_id[c["tool_use_id"]]
                s["is_error"] = bool(c.get("is_error"))
                if isinstance(tur, dict) and tur.get("resolvedModel"):
                    s["model"] = tur["resolvedModel"]
                if not (isinstance(tur, dict) and tur.get("isAsync")):  # sync spawn: the result is the report
                    s["report"], s["status"] = _text(c.get("content")), s["status"] or "completed"
        text = _text(content)
        attachment = d.get("attachment")
        if isinstance(attachment, dict) and isinstance(attachment.get("prompt"), str):
            text += attachment["prompt"]  # notifications that land while the orchestrator is busy are queued
        if "<task-notification>" in text:
            for block in NOTIFY.findall(text):  # fields are read inside one block, never across two
                tid, status = (FIELD[k].search(block) for k in ("tool-use-id", "status"))
                if tid and status and tid.group(1).strip() in by_id:
                    s = by_id[tid.group(1).strip()]
                    result = RESULT.search(block)
                    s["status"], s["report"] = status.group(1).strip(), result.group(1) if result else s["report"]
    return spawns


def propose(spawns: list) -> list:
    out = []
    for i, s in enumerate(spawns):
        if s["status"] is None and not s["is_error"]:
            continue  # still running, or the session ended first
        tier = tier_of(s["main_model"] if s["model"] == "inherit" else s["model"])
        outcome, reason, doubtful = "succeeded", "finished, no redo", False
        if s["is_error"]:
            outcome, reason = "failed", "tool error"
        elif s["status"] in ("failed", "stopped"):
            outcome, reason = "failed", f"status {s['status']}"
        elif BLOCKED.search(s["report"][-2000:]):
            outcome, reason, doubtful = "failed", "report says blocked", True
        else:
            task = primary(s["brief"])
            for later in spawns[i + 1:] if task else []:
                if primary(later["brief"]) != task:
                    continue
                if REDO.search(later["brief"][:HEAD]):
                    outcome, reason = "failed", f"redone later ({task})"
                    break
                if role(later["brief"]) == role(s["brief"]):
                    outcome, reason, doubtful = "failed", f"re-spawned for {task}", True
                    break
        out.append({"id": s["id"], "ts": s["ts"], "brief": s["brief"], "tier": tier, "outcome": outcome,
                    "reason": reason, "doubtful": doubtful})
    return out


def apply(log_path: Path, proposals: list) -> int:
    """Write proposals into agent entries without an outcome; returns how many entries changed."""
    by_id = {p["id"]: p for p in proposals}
    heads = [p["brief"][:2000] for p in proposals]
    # A brief spawned twice (a redo) can't say which entry is which, so brief matching skips it: guessing would
    # write the retry's "succeeded" over the failure, and failures are the scarce label.
    by_brief = {p["brief"][:2000]: p for p in proposals if heads.count(p["brief"][:2000]) == 1}
    lines = log_path.read_text(encoding="utf-8").splitlines()
    briefs = []  # agent-entry prompts, to spot duplicates on the log side too
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("source") == "agent":
            briefs.append(e.get("prompt"))
    changed, out = 0, []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            out.append(line)
            continue
        p = None
        # auto proposals are refreshed (the heuristics improve); a user-confirmed outcome is never touched
        if isinstance(e, dict) and e.get("source") == "agent" and (not e.get("outcome") or e.get("outcome_source") == "auto"):
            p = by_id.get(e.get("tool_use_id")) or (by_brief.get(e.get("prompt")) if briefs.count(e.get("prompt")) == 1 else None)
        if p:
            e.update(outcome=p["outcome"], outcome_reason=p["reason"], outcome_tier=p["tier"],
                     outcome_source="auto", outcome_doubtful=p["doubtful"])
            line, changed = json.dumps(e, ensure_ascii=False), changed + 1
        out.append(line)
    # Other sessions may append while we work: keep any lines that arrived after the read.
    tmp = log_path.with_name(log_path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    late = log_path.read_text(encoding="utf-8").splitlines()[len(lines):]
    if late:
        with tmp.open("a", encoding="utf-8") as f:
            f.write("\n".join(late) + "\n")
    os.replace(tmp, log_path)
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--projects-dir", type=Path, default=Path.home() / ".claude" / "projects")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    cutoff = time.time() - args.days * 86400
    proposals = []
    for path in sorted(args.projects_dir.glob("*/*.jsonl")):
        if path.stat().st_mtime >= cutoff:
            proposals += propose(scan(path))
    failed = [p for p in proposals if p["outcome"] == "failed"]
    doubtful = [p for p in proposals if p["doubtful"]]
    summary = {"spawns": len(proposals), "failed": len(failed), "succeeded": len(proposals) - len(failed),
               "doubtful": len(doubtful)}
    if args.apply:
        try:
            summary["log_entries_updated"] = apply(Path(load_config().routing_log_file).expanduser(), proposals)
        except (ConfigError, OSError) as e:
            print(f"cannot update the routing log: {e}")
            return 1
    if args.json:
        print(json.dumps({**summary, "doubtful_list": [{k: p[k] for k in ("id", "ts", "tier", "outcome", "reason")}
                                                       for p in doubtful]}, indent=2))
        return 0
    print(", ".join(f"{k} {v}" for k, v in summary.items()))
    for n, p in enumerate(doubtful, 1):  # local only: brief heads help the user decide
        print(f"  {n:>3}. {p['ts'][:10]} {p['tier'] or '?':6} {p['outcome']:9} {p['reason']:28} {' '.join(p['brief'].split())[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
