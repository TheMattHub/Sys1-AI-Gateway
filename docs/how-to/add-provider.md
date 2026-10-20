# Add a provider

A provider is one small adapter file that maps the gateway's neutral request to one engine's API. Only the
adapter knows the engine: the MCP tools, the schema and the gateway stay the same. In Claude Code,
`/system1:add-provider` walks through these steps in a git clone; here `myengine` stands for the engine you
add.

## 1. Write the adapter

Create `system1_gateway/providers/myengine.py` with a subclass of `System1Provider` (see
[base.py](../../system1_gateway/providers/base.py)). The existing adapters are the examples to copy:
[laya.py](../../system1_gateway/providers/laya.py) for a local HTTP engine,
[mock.py](../../system1_gateway/providers/mock.py) for an in-process one.

- `name = "myengine"`, and the engine's native contract in the module docstring.
- The constructor validates the settings and raises `ValueError` for unusable ones; the gateway reports
  those as `config_error`.
- `decide(request, timeout_s)` returns `{"decision", "confidence", "rationale"}` (confidence in 0..1) or
  `{"abstain": True, "rationale"}`. Raise `ProviderError` for transport failures and `MalformedResponse`
  for a reply you cannot read; the gateway checks the rest.
- Pass `timeout_s` to every I/O call: a timed-out thread cannot be killed.
- `health(timeout_s)` returns `{"ok": bool, "detail": str}`; `capabilities()` returns non-secret facts,
  including `max_options` if the engine has a limit.
- For HTTP engines, [http.py](../../system1_gateway/providers/http.py) gives you the loopback guard, the
  `allow_remote` opt-in, no proxy for local calls, and typed errors.

Keep it stdlib only. Secrets come from environment variables (`SYSTEM1_MYENGINE_API_KEY`), never the config.

## 2. Register it

Add `"myengine": MyEngineProvider` to `REGISTRY` in
[providers/\_\_init\_\_.py](../../system1_gateway/providers/__init__.py), and a commented
`[providers.myengine]` section to [config.example.toml](../../config.example.toml).

## 3. Test it

Add `tests/test_myengine.py`. For an HTTP engine, serve a fake on `127.0.0.1` (port 0), modelled on
[tests/fake_laya.py](../../tests/fake_laya.py); tests make no real network calls. Cover the mapping, an
abstention, a transport error, a bad body, a timeout, an invalid setting and `health`. Then run the suite:

```sh
python -m unittest discover -s tests -v
```

## 4. Use it

Re-run the installer, set `provider = "myengine"` or add it to `fallback`, and check it:

```sh
<venv python> scripts/smoke.py --question "Rerun or block?" --options rerun block
```

Contributions are welcome; see [CONTRIBUTING.md](../../CONTRIBUTING.md).
