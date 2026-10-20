"""Pause or resume System-1 everywhere, or show its state.

    python scripts/toggle.py on | off | status

off creates the pause file: from the next prompt both hooks stay quiet and system1_decide abstains, with no restart.
Turning a feature on for the first time is /system1:setup's job; this only pauses what the config enables.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from system1_gateway.config import ConfigError, load_config  # noqa: E402
from system1_gateway.gateway import Gateway  # noqa: E402


def today_counts(log_file: str) -> Counter:
    """(source, tier or status) -> entries logged today."""
    today, counts = time.strftime("%Y-%m-%d"), Counter()
    try:
        lines = Path(log_file).expanduser().read_text(encoding="utf-8").splitlines()
    except OSError:
        return counts
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and str(e.get("ts", "")).startswith(today):
            counts[(e.get("source", "prompt"), str(e.get("decision") or e.get("status")).split(": ", 1)[0])] += 1
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", nargs="?", default="status", choices=("on", "off", "status"))
    action = parser.parse_args(argv).action
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"config error: {e}")
        return 1
    pause = Path(cfg.pause_file)
    features = {"routing": (cfg.routing_enabled, cfg.routing_hint), "skill picker": (cfg.skills_enabled, cfg.skills_hint)}
    if action == "off":
        pause.parent.mkdir(parents=True, exist_ok=True)
        pause.touch()
        print("System-1 paused: from the next prompt the hooks stay quiet and system1_decide abstains. "
              "/system1:toggle on resumes it.")
    elif action == "on":
        pause.unlink(missing_ok=True)
        print("System-1 active from the next prompt.")
        if not any(enabled for enabled, _ in features.values()):
            print("Note: every feature is disabled in the config, so nothing will run. Enable one with /system1:setup.")
    else:
        print(f"System-1: {'paused' if cfg.paused() else 'active'}")
        for name, (enabled, hint) in features.items():
            print(f"  {name}: {'on' if enabled else 'off'}" + (f" (hint {'on' if hint else 'off'})" if enabled else ""))
        health = Gateway(cfg).health()
        for p in health["providers"]:
            print(f"  provider {p['name']} ({p['role']}): {'ok' if p['ok'] else 'down'} - {p['detail']}")
        counts = today_counts(cfg.routing_log_file)
        print("  today: " + (", ".join(f"{s}/{t} {n}" for (s, t), n in sorted(counts.items())) or "nothing logged"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
