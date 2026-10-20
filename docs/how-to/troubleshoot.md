# Troubleshoot

When the gateway misbehaves, check one layer at a time from the top and stop at the first that fails. In
Claude Code, `/system1:doctor` does exactly this, shows the evidence and asks before fixing anything. The
session-start hook also speaks up when the gateway is not installed, the config is broken, or routing is on
but the engine is not running.

## 1. Is it registered?

`claude mcp get system1` must show the venv Python followed by `-I -m system1_gateway`, at user scope. If it
is missing, run `/system1:setup` or [register it](install.md#register-with-claude-code). A project-scope or
`.mcp.json` entry can shadow it.

## 2. Does the command start?

```sh
<venv python> scripts/smoke.py
```

`smoke.py` launches the installed gateway exactly as an MCP client does and checks the handshake and
health; add `--question "..." --options a b` for one decision, or `--python <path>` to test another
interpreter. It runs on any Python 3.8+.

| Output | Cause | Fix |
|---|---|---|
| `NOT INSTALLED` | the venv is missing | re-run the installer |
| `No module named system1_gateway` | the package was not copied into the venv | re-run the installer |
| Python will not start | the base Python was upgraded or removed under the venv | re-run the installer; it rebuilds the venv |
| `HANDSHAKE FAILED` with a traceback | a code bug | run the tests and read the traceback |

## 3. What does health say?

- **`config_errors`:** the message names the file and the key: a TOML syntax error, an unknown key,
  `timeout_s` not above 0, `min_confidence` outside [0, 1], an unknown provider, or a non-local endpoint
  without `allow_remote`. `SYSTEM1_*` environment variables override the file, so check those too.
- **A provider with `ok: false`:** is the engine running, on the configured port? Laya answers
  `GET <endpoint>/health`. To tell a gateway problem from an engine problem, run `python tests/fake_laya.py
  --port <port>` from a clone; if smoke then passes, the problem is on the engine's side.
- **`degraded`:** the primary is down and a fallback answered. Fix the primary.
- **`paused`:** `/system1:toggle on` resumes it.

## 4. What do the decisions say?

Run smoke with a question and read `attempts[].outcome` and `detail`:

- **`timeout`:** compare the engine's latency with `timeout_s`; raise it only if the engine really is that slow.
- **`malformed`:** the reply does not match what the adapter expects, often a newer engine version. Compare
  a raw reply with the adapter's docstring, and update it with [Add a provider](add-provider.md).
- **Always `abstained`:** confidence is below `min_confidence`. That is correct behaviour; lower the threshold
  only if less certain answers are acceptable.
- **`error`:** read `detail` (HTTP status, connection refused, ...).

## Routing gives no hints

Check that `[routing] enabled = true`, that `hint` is not `false`, and that the engine is up. Then run the hook
by hand: `echo '{"prompt": "Write unit tests for the parser module"}' | <venv python> -I -m
system1_gateway.route_hook`. JSON output means it works; no output means the engine abstained or failed.
On Windows the hook runs through Git Bash, so paths in environment variables must be Windows-style (`C:/...`).

For more detail, set `SYSTEM1_LOG_LEVEL=DEBUG` (it also logs question text) or `log_file`, and start Claude
Code with `claude --debug` to see the server's stderr.
