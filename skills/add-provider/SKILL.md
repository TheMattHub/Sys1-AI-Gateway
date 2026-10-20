---
name: add-provider
disable-model-invocation: true
description: Add or rewrite a System-1 provider adapter (AnyJev, a remote API, or Laya's real contract).
---

# Add or adapt a System-1 provider

Principle: **only the adapter knows the engine.** Don't change `schema.py`, `server.py`, `gateway.py` or the tool definitions. If the engine needs something the v1 schema can't express, stop and discuss it with the user first, because it would mean a schema version bump.

## 0. Work in a git clone, never in the plugin copy
This changes source code, so it needs a writable git clone of the gateway repo. If this skill's base directory is inside `~/.claude/plugins/` (a plugin copy that gets replaced on update), ask the user for their clone's path. If they don't have one, ask before cloning. Do all the steps below in the clone.

## 1. Gather the contract (ask for whatever is unknown; don't guess silently)
- Provider name: lowercase, one word, e.g. `anyjev`. This becomes the config section `[providers.anyjev]` and the env prefix `SYSTEM1_ANYJEV_`.
- Transport: local HTTP / in-process Python library / CLI subprocess / remote HTTP API.
- Native request, native response (confidence scale? abstain signal?), and a health probe.
- Settings and defaults.
  - **Secrets only via env vars** (`SYSTEM1_ANYJEV_API_KEY`). Never put them in config, the repo, or logs.
  - Remote endpoints must be opt-in: copy Laya's loopback check plus `allow_remote`.

If the user has a sample request or response, or docs, read them. For an existing adapter (e.g. the real Laya arriving), also capture a live reply from the engine.

## 2. Implement `system1_gateway/providers/<name>.py`
Model it on `providers/laya.py` (HTTP) or `providers/mock.py` (in-process):
- Subclass `System1Provider` and set `name = "<name>"`. Put the native contract in the module docstring.
- **Constructor:** validate settings and raise `ValueError` for unusable ones (the gateway reports these as `config_error`). Coerce env-string settings; `as_bool` is available.
- **`decide(request, timeout_s)`:** map `request.question/options/context` to the native request. Map the native reply to `{"decision", "confidence" (0..1), "rationale"}` or `{"abstain": True, "rationale"}`. Rescale confidence if the engine uses another scale.
- **Pass `timeout_s` to every I/O call** (urllib `timeout=`, `subprocess.run(timeout=)`, ...). Timed-out threads can't be killed.
- **Errors:** raise `ProviderError` for transport/HTTP failures and `MalformedResponse` for non-JSON or unexpected shapes. You don't need to re-validate the neutral output; the gateway does it.
- `health(timeout_s)` returns `{"ok": bool, "detail": str}`. `capabilities()` returns non-secret facts only.
- Stdlib only. Adding a dependency needs the user's OK, plus changes to both install scripts and `pyproject.toml`.

## 3. Register and document
- Add one line to `REGISTRY` in `providers/__init__.py`.
- Add a commented `[providers.<name>]` section to `config.example.toml`.
- Add a short subsection to `README.md` with the contract and settings.

## 4. Test: `tests/test_<name>.py`
- **HTTP engines:** a local fake server modeled on `tests/fake_laya.py` (serve on 127.0.0.1, port 0). **No real network calls in tests.**
- **CLI/library engines:** a stub script or `unittest.mock`.
- Cover:
  - the native→neutral mapping
  - abstain mapping
  - an HTTP/transport error → `provider_error`
  - a bad body → `malformed_response`
  - timeout → `provider_timeout`
  - an invalid setting → `config_error`
  - `health`
- Run `<venv python> -m unittest discover -s tests`. All tests must pass, old and new.

## 5. Roll out
- Re-run the installer, which copies the updated package into the venv.
- Ask whether to make it the `provider` or add it to `fallback` in the user config.
- Verify with `<venv python> scripts/smoke.py --question ... --options ...`.
- To ship it to other machines, the user commits and pushes (don't do it yourself), then on each machine updates the plugin and runs `/system1:setup` (upgrade).
- Don't commit. Summarize the changed files for the user.
