"""Claude Code SessionStart hook: tell the user when the System-1 setup needs attention; otherwise stay silent.

hooks/session handles "gateway not installed" itself (this module cannot run then). Here: config errors,
and routing enabled while the provider is down (typically: the engine was not started after a reboot).

    python -I -m system1_gateway.session_hook
"""

import json
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .gateway import Gateway

HEALTH_TIMEOUT_S = 1.0  # never hold up session start for long (Windows takes ~2 s to refuse a closed port)
CALIBRATE_EVERY = 30  # unlabeled routing-log entries that make a calibration round worth it


def unlabeled_count(log_file: str) -> int:
    try:
        with Path(log_file).expanduser().open(encoding="utf-8") as f:
            # skill-picker entries have their own labels (a skill name), so they don't count toward routing's round;
            # an entry with feature labels is labeled for the feature questions even without a tier label
            return sum(1 for line in f if line.strip() and (e := json.loads(line)).get("label") is None
                       and not e.get("feature_labels") and e.get("source") != "skill")
    except (OSError, ValueError):
        return 0


def message() -> str | None:
    try:
        config = load_config()
    except ConfigError as e:
        return f"System-1: config error ({e}). Run /system1:doctor."
    if not config.routing_enabled or config.paused():  # a deliberate pause isn't a down engine
        return None
    config.timeout_s = min(config.timeout_s, HEALTH_TIMEOUT_S)
    health = Gateway(config).health()
    if health["status"] == "ok":
        pending = unlabeled_count(config.routing_log_file) if config.routing_log_dirs else 0
        if pending >= CALIBRATE_EVERY:
            return (f"System-1: {pending} routing prompts are waiting to be labeled. Run /system1:calibrate "
                    f"to label them and refit the confidence calibration.")
        return None
    if health["config_errors"]:
        return f"System-1: config error ({'; '.join(health['config_errors'])}). Run /system1:doctor."
    down = next((p for p in health["providers"] if not p["ok"]), {})
    return (f"System-1 routing is on, but provider {down.get('name', '?')!r} is {health['status']}, so no "
            f"routing hints this session. Start the engine (Laya: ~/.system1-gateway/engines/laya/start.ps1 "
            f"or start.sh) or run /system1:doctor.")


def main():
    text = message()
    if text:
        sys.stdout.reconfigure(encoding="utf-8")
        json.dump({"systemMessage": text}, sys.stdout)


if __name__ == "__main__":
    main()
