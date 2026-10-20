"""Claude Code hooks: route a task to a Claude model tier from text-visible features.

System-1 answers four yes/no questions about the text (routing_features.py) in one engine pass, and the user-owned
rule in routing_rule.py maps them to a tier (spec 2026-09-30). QUESTION/TIERS below are the retired single tier
question, kept so scripts/calibrate.py can still read old tier labels.
UserPromptSubmit: the tier is injected as advisory context, so Claude can pass it as the `model` of subagents
it spawns (unless [routing] hint = false). It never blocks or rewrites the prompt. It stays silent when routing
is disabled (the default), the prompt is too short or a slash command, System-1 abstains, or anything fails.
PreToolUse on Agent: record-only. System-1's tier for the subagent's task is logged next to the orchestrator's
choice, as calibration data; nothing is printed and the spawn is never changed.
Skill picker ([skills] enabled): on the same prompt, System-1 names the skill that fits, as a one-line hint (or a log
entry only, while [skills] hint = false). Dormant, with no engine call, while the provider's max_options can't hold
every skill Claude could load.

    python -I -m system1_gateway.route_hook < hook_input.json
"""

import json
import sys
import time
import uuid
from pathlib import Path

from .config import ConfigError, load_config
from .gateway import Gateway
from .routing_features import MAX_PROMPT_CHARS, ask_features
from .routing_rule import tier as rule_tier
from .schema import MAX_OPTIONS
from .skill_index import available_skills

QUESTION = "Which Claude model should handle this task?"
# Full sentences give the decision model something to match against; the tier is the part before ':'.
TIERS = [
    "haiku: quick mechanical work such as renames, formatting, lookups, small edits or simple questions",
    "sonnet: well-specified implementation, writing tests, or fixing a bug of moderate size",
    "opus: complex design, architecture, large refactors, research or subtle debugging",
]
# Under 10 words a prompt is usually a follow-up ("Plan is ok, implement") whose size depends on the conversation,
# which the hook can't see: 0/3 right on the labeled 4-8-word prompts. Claude decides those unaided.
MIN_WORDS = 10
# Subagent hand-backs arrive as prompts, but they are reports, not tasks: the model answered their fixed
# header (sonnet on 79 of 84 notifications), and no tier label fits them, so they are neither routed nor logged.
HARNESS_PREFIXES = ("<agent-message", "<task-notification")
# Runs before every prompt: a warm engine answers in ~0.25 s, and a down one must not stall the user
# (Windows takes ~2 s to refuse a closed port).
TIMEOUT_S = 1.5


def should_log(cwd, log_dirs: list) -> bool:
    """True if the session's working directory is one of log_dirs or inside one."""
    if not isinstance(cwd, str) or not cwd:
        return False
    here = Path(cwd).expanduser().resolve()
    for d in log_dirs:
        root = Path(d).expanduser().resolve()
        if here == root or root in here.parents:  # WindowsPath compares case-insensitively
            return True
    return False


def request_for(prompt: str, min_confidence: float | None = None) -> dict:
    """The gateway request for a prompt; scripts/calibrate.py builds the same one, so fits match live use."""
    req = {"question": QUESTION, "options": TIERS, "context": {"task": prompt[:MAX_PROMPT_CHARS]}}
    if min_confidence is not None:
        req["min_confidence"] = min_confidence
    return req


def _task_prompt(payload) -> str | None:
    """The prompt to route, cut to MAX_PROMPT_CHARS; None for slash commands, hand-backs and short follow-ups."""
    prompt = payload.get("prompt") if isinstance(payload, dict) else None
    if (not isinstance(prompt, str) or prompt.lstrip().startswith(("/", *HARNESS_PREFIXES))
            or len(prompt.split()) < MIN_WORDS):
        return None
    return prompt[:MAX_PROMPT_CHARS]


def classify(gateway, text: str) -> dict:
    """Ask the features in one engine pass and apply the tier rule. The result has the fields _log reads."""
    started = time.monotonic()
    features = ask_features(gateway, text)
    tier = rule_tier({k: v["answer"] for k, v in features.items()})
    confidences = [v["confidence"] for v in features.values()]
    if tier:
        status = "decided"
    else:
        # no tier because a question failed is an error; "abstained" means the engine itself declined
        status = "error" if any(v["status"] == "error" for v in features.values()) else "abstained"
    provider = gateway.chain[0].name if getattr(gateway, "chain", None) else None
    return {"request_id": uuid.uuid4().hex, "status": status, "decision": tier, "provider": provider,
            "confidence": min(confidences) if tier and None not in confidences else None,
            "rationale": ", ".join(f"{k}={v['answer'] or '-'}" + (f" {v['confidence']:.2f}" if v["confidence"] is not None else "")
                                   for k, v in features.items()),
            "features": features, "latency_ms": int((time.monotonic() - started) * 1000)}


def route(payload: dict, gateway: Gateway, log_file: str = "", log_dirs: tuple = (),
          min_confidence: float | None = None, hint: bool = True) -> str | None:
    """Return the hint to inject, or None. Logs only when payload["cwd"] is inside log_dirs.
    With hint=False it only logs, and asks nothing when there is nothing to log."""
    prompt = _task_prompt(payload)
    if prompt is None:
        return None
    log_it = bool(log_file) and should_log(payload.get("cwd"), log_dirs)
    if not (hint or log_it):
        return None
    result = classify(gateway, prompt)
    if log_it:
        _log(log_file, prompt, result, payload.get("cwd"), features=result["features"], rule_tier=result["decision"])
    threshold = min_confidence if min_confidence is not None else gateway.config.min_confidence
    if not hint or result["status"] != "decided" or result["confidence"] is None or result["confidence"] < threshold:
        return None
    tier = result["decision"]
    return (f"System-1 routing hint ({result['provider']}, confidence {result['confidence']:.2f}): suggested "
            f"model tier for this task is **{tier}**. When you spawn subagents for it, prefer model=\"{tier}\" "
            f"unless you have a concrete reason to pick another. This is advisory; ignore it if it is clearly wrong.")


def record_spawn(payload: dict, gateway: Gateway, log_file: str = "", log_dirs: tuple = ()) -> None:
    """Log System-1's tier for a subagent's task next to the tier the orchestrator chose. Prints nothing.

    Asked with min_confidence 0 so every entry holds System-1's top answer; a threshold from the calibration is
    applied afterwards, when judging whether hints would have helped.
    """
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    task = tool_input.get("prompt") if isinstance(tool_input, dict) else None
    if not isinstance(task, str) or not task.strip() or not log_file or not should_log(payload.get("cwd"), log_dirs):
        return
    task = task[:MAX_PROMPT_CHARS]
    result = classify(gateway, task)
    # "inherit": no model given, so the subagent runs on the orchestrator's own model
    _log(log_file, task, result, payload.get("cwd"), source="agent", chosen=tool_input.get("model") or "inherit",
         subagent_type=tool_input.get("subagent_type") or "general-purpose", tool_use_id=payload.get("tool_use_id"),
         features=result["features"], rule_tier=result["decision"])


SKILL_QUESTION = "Which skill should Claude load for this task?"
NO_SKILL = "none: no listed skill fits; answer directly"
SKILL_OPTION_CHARS = 200


def pick_skill(payload, gateway, skills=None, log_file: str = "", log_dirs: tuple = (),
               min_confidence: float = 0.8, hint: bool = False) -> str | None:
    """Return a skill hint, or None. Dormant (no engine call) while the provider can't take every skill as an option."""
    prompt = _task_prompt(payload)
    log_it = bool(log_file) and prompt is not None and should_log(payload.get("cwd"), log_dirs)
    if prompt is None or not (hint or log_it):
        return None
    skills = available_skills(payload, payload.get("cwd")) if skills is None else skills
    # "name: description"; names may hold ":" (plugin:skill), so the name is the part before ": "
    options = list(dict.fromkeys([NO_SKILL, *((f"{n}: {d}" if d else n)[:SKILL_OPTION_CHARS] for n, d in skills)]))
    limit = getattr(gateway, "max_options", lambda: None)()
    if len(options) < 2 or len(options) > min(limit or MAX_OPTIONS, MAX_OPTIONS):
        return None
    result = gateway.decide({"question": SKILL_QUESTION, "options": options, "context": {"task": prompt},
                             "min_confidence": min_confidence})
    if log_it:
        _log(log_file, prompt, result, payload.get("cwd"), source="skill")
    if not hint or result["status"] != "decided" or result["decision"] == NO_SKILL:
        return None
    name = result["decision"].split(": ", 1)[0]
    return (f"System-1 skill hint (confidence {result['confidence']:.2f}): consider the `{name}` skill if it fits "
            f"this task; ignore this if it doesn't.")


def _log(log_file: str, prompt: str, result: dict, cwd: str, **extra):
    # Local-only record for calibration; "label" is left for the user to fill in with the right tier.
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "request_id": result["request_id"], "cwd": cwd, "prompt": prompt,
             "status": result["status"], "decision": result["decision"], "confidence": result["confidence"],
             "rationale": result["rationale"], **extra, "label": None}
    try:
        path = Path(log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # a logging failure must never disturb the user's prompt


def main():
    started = time.monotonic()
    try:
        config = load_config()
        if config.paused() or not (config.routing_enabled or config.skills_enabled):
            return
        payload = json.loads(sys.stdin.buffer.read() or b"{}")
        config.timeout_s = min(config.timeout_s, TIMEOUT_S)
        gateway = Gateway(config)
        if isinstance(payload, dict) and payload.get("hook_event_name") == "PreToolUse":
            if config.routing_enabled:
                record_spawn(payload, gateway, config.routing_log_file, config.routing_log_dirs)
            return
        hints = []
        if config.routing_enabled:
            hints.append(route(payload, gateway, config.routing_log_file, config.routing_log_dirs,
                               config.routing_min_confidence, config.routing_hint))
        # One budget for both questions: the prompt never waits more than TIMEOUT_S for the engine.
        left = TIMEOUT_S - (time.monotonic() - started)
        if config.skills_enabled and left > 0.2:
            config.timeout_s = min(config.timeout_s, left)  # Gateway reads its config on every decide
            hints.append(pick_skill(payload, gateway, None, config.routing_log_file, config.routing_log_dirs,
                                    config.skills_min_confidence, config.skills_hint))
        hint = "\n".join(h for h in hints if h)
    except (ConfigError, ValueError, OSError):
        return
    if hint:
        sys.stdout.reconfigure(encoding="utf-8")
        json.dump({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": hint}},
                  sys.stdout)


if __name__ == "__main__":
    main()
