---
name: toggle
disable-model-invocation: true
argument-hint: on | off | status
description: Pause or resume System-1 (routing hook, skill picker and system1_decide), or show its status.
---

# System-1 on/off

Gateway root (holds `scripts/`): two directories above this skill's base directory. Venv Python: `~/.system1-gateway/venv/Scripts/python.exe` (Windows) or `~/.system1-gateway/venv/bin/python`.

Run `<venv python> scripts/toggle.py $ARGUMENTS` from the gateway root (no argument means `status`) and show its output as is. `on` and `off` take effect from the next prompt, with no restart. Laya runs locally, so pausing is about speed and noise, not privacy.
