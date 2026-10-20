---
name: doctor
description: Diagnose a broken System-1 gateway - system1 MCP server missing or not connecting, health down/degraded, config_error, timeouts, malformed answers, or constant abstaining.
---

# System-1 gateway doctor

Diagnose top-down and stop at the first broken layer. Show the evidence (command and output) for each finding. **Propose fixes and ask before applying them.** The exceptions are read-only checks, and re-running the installer, which is safe and idempotent.

Gateway root (holds `scripts/`, `tests/`, `system1_gateway/`): two directories above this skill's base directory. Run the scripts below from there.

Venv Python: `~/.system1-gateway/venv/Scripts/python.exe` (Windows) or `~/.system1-gateway/venv/bin/python`. User config: `%APPDATA%\system1\config.toml` or `~/.config/system1/config.toml`, unless `SYSTEM1_CONFIG` is set.

## 1. Registration
`claude mcp get system1`
- **Not found:** it was never registered. Use `/system1:setup`, step 7.
- The command must be the venv Python followed by `-I -m system1_gateway`, and the scope must be *user*.
  - A different path (e.g. an old machine or user): re-register.
  - A project-scope or `.mcp.json` entry shadowing it: tell the user where it is and don't delete it without asking.

## 2. Does the exact command start?
`<py> scripts/smoke.py` (add `--python <path>` to test the registered command's interpreter).
`<py>` is the venv Python if it exists. Otherwise any Python 3.8+ works, since smoke.py itself doesn't need 3.11: `py -3` on Windows (bare `python`/`python3` may be the Microsoft Store stub), `python3` on Unix.

| Output | Cause | Fix |
|---|---|---|
| `NOT INSTALLED` | the venv is missing | re-run the installer |
| `No module named system1_gateway` | the package wasn't copied into the venv | re-run the installer |
| Python won't start / "no Python at ..." | the base Python was upgraded or removed under the venv | re-run the installer; it rebuilds the venv with the current Python |
| `HANDSHAKE FAILED` + traceback in stderr | a code bug | run the tests (`<venv python> -m unittest discover -s tests`) and read the traceback |

## 3. Health (from the smoke output)
- **`config_errors` present:** the message names the file and the key. Common causes:
  - a TOML syntax error
  - an unknown `[gateway]` key (typo)
  - `timeout_s` ≤ 0
  - `min_confidence` outside [0, 1]
  - an unknown provider name
  - a Laya endpoint that isn't local while `allow_remote` is unset

  Also check `SYSTEM1_*` env vars: `Get-ChildItem env:SYSTEM1_*` / `env | grep ^SYSTEM1_`. They override the file.
- **Provider `ok: false`:**
  - Laya: is it running? Probe it with `curl <endpoint>/v1/health`. Does the port match? Local calls deliberately bypass proxies.
  - To separate a gateway problem from a Laya problem, run `<py> tests/fake_laya.py --port <port>` on the configured port. If smoke then passes, the problem is Laya's side or its contract. Stop the fake server afterwards.
- **`degraded`:** the primary is down and a fallback answered. Fix the primary.

## 4. Decision quality (`--question ... --options ...`)
Look at `attempts[].outcome` and `detail`:
- **`timeout`:** compare the provider's latency with `timeout_s`. Raise `timeout_s` only if the provider really is that slow.
- **`malformed`:** the provider's reply doesn't match what the adapter expects. The adapter was verified against laya 0.3.20; a newer Laya may have changed its format. Capture a raw reply (e.g. `curl -X POST <endpoint>/v1/systemone -H "Content-Type: application/json" -d '{"model":"typed-decisions","state":{},"questions":{"decision":{"type":"choice","instructions":"test?","criteria":["a","b"]}}}'`), compare it with the docstring in `system1_gateway/providers/laya.py`, and if it differs ask the user to run `/system1:add-provider`.
- **Always `abstained`:** confidences are below `min_confidence`. That's correct behaviour. Only lower the threshold if the user accepts less certain answers; fallback is deliberately not triggered by low confidence.
- **`error`:** read `detail` (HTTP status, connection refused, ...).

## Routing hook gives no hints
The hook is silent by design, so check each layer:
1. `[routing] enabled = true` in the user config.
2. `claude plugin details system1` lists the hook (plugin 0.1.4+).
3. Run it by hand: `echo '{"prompt": "Write unit tests for the parser module"}' | <venv python> -I -m system1_gateway.route_hook`. JSON output means it works. No output means the provider abstained or failed, so check health and the `routing.jsonl` log.

On Windows the hook runs through Git Bash, so paths passed in env vars must be Windows-style (`C:/...`), not `/c/...` or `/tmp/...`.

## 5. More detail
- Set `SYSTEM1_LOG_LEVEL=DEBUG` (this also logs question text) and/or `log_file` in the config.
- `claude --debug` shows the MCP server's stderr inside Claude Code.
- Every log line carries the `request_id` returned in the response.

Finish with: the layer that failed, the root cause, the fix (applied or proposed), and the smoke result after the fix.
