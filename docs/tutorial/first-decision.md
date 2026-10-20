# Your first decision

This tutorial takes you from nothing to one `system1_decide` call in Claude Code, in about five minutes
plus the engine download. You need Claude Code and Python 3.11 or later; you do not need a clone of this
repository. At the end you will know which engine you run and how to check it.

## 1. Install the plugin

The repository is both a Claude Code plugin (`system1`) and its own marketplace (`system1-gateway`). In
Claude Code, run:

```
/plugin marketplace add TheMattHub/Sys1-AI-Gateway
/plugin install system1@system1-gateway
```

The next session greets you with a one-line pointer to `/system1:setup`.

## 2. Run the setup

```
/system1:setup
```

The setup checks for Python 3.11+, installs the gateway into `~/.system1-gateway/venv`, runs the tests and
registers the `system1` MCP server at user scope, so it works in every project. It asks before each change
outside the plugin. When it asks for a provider, you have three ways on:

- **You already run Laya:** give its endpoint (default `http://127.0.0.1:8765`).
- **No engine yet:** let it hand over to `/system1:choose-model`, which profiles your hardware, recommends an
  engine and installs it on a yes. The [study](../studies/naga-decisions.md) helps you choose.
- **Just trying it:** pick `mock`, a deterministic stand-in that always picks the first option. Setup can
  also start a fake Laya for one smoke test and stop it again.

Setup ends with a smoke test: it starts the gateway exactly as Claude Code does and asks one question.

## 3. Restart Claude Code

The MCP server loads in new sessions only. After the restart, `/mcp` lists `system1` as connected.

## 4. Ask it something

Ask Claude for a judgement call, for example: "Use system1_decide: rerun the flaky pipeline or block the
merge?" Claude calls the tool with a question and the options:

```json
{"question": "Rerun the flaky pipeline or block the merge?",
 "options": ["rerun the pipeline", "block the merge"]}
```

With the `mock` provider the answer is (latencies set to 0):

```json
{"schema_version": "1", "request_id": "demo-1", "status": "decided",
 "decision": "rerun the pipeline", "confidence": 0.9,
 "rationale": "mock provider: always picks the first option", "provider": "mock",
 "probabilities": {"rerun the pipeline": 0.9, "block the merge": 0.09999999999999998},
 "calibrated": false, "latency_ms": 0,
 "attempts": [{"provider": "mock", "outcome": "ok", "latency_ms": 0, "detail": null}], "error": null}
```

With a real engine, `provider`, `confidence` and `rationale` come from it, and `calibrated` is `true` when a
fitted calibration matches the engine and checkpoint. If the status is `abstained`, the engine was not sure
enough, and Claude decides itself; that is a valid answer, not a failure.

## Next

- Install a real engine: [Install an engine](../how-to/engines.md).
- Let System-1 suggest a Claude model for subagents: [Turn on model routing](../how-to/routing.md).
- Something did not connect: [Troubleshoot](../how-to/troubleshoot.md).
