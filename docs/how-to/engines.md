# Install an engine

An engine is the local model that actually answers; the gateway only talks to it. The easiest path is
`/system1:choose-model`: it profiles your hardware and preferences, checks the current models online,
recommends one checkpoint and installs it on a yes, each engine in its own venv under
`~/.system1-gateway/engines/`. This page shows what it sets up, for when you want to do it by hand.

Which engine to pick is a question of speed, accuracy and hardware, measured in the
[naga decisions study](../studies/naga-decisions.md). The gateway has adapters for three real engines:

| Provider | Engine | Start it | Notes |
|---|---|---|---|
| `laya` | Laya `typed-decisions` | `~/.system1-gateway/engines/laya/start.ps1` or `start.sh` | one pass for several questions; at most 20 options |
| `von` | Von 1.3 (`pip install von-sdk`) | `von serve --host 127.0.0.1 --port 8777` | one pass; 8,192-token context; no option limit declared |
| `ollama` | any local chat model | Ollama 0.12 or later (for logprobs) | one call per question; at most 26 options |

Some engines in the study have no adapter here yet (the rerankers and the hosted Claude Haiku); add one
with [Add a provider](add-provider.md).

## Laya

[Laya](https://huggingface.co/convaiinnovations/laya) (Convai, Apache-2.0) runs as its own local server,
`laya-serve`, in a separate venv. `/system1:choose-model` installs it into
`~/.system1-gateway/engines/laya/` with a launcher copied from [engines/laya/](../../engines/laya/):

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.system1-gateway\engines\laya\start.ps1"   # -Model, -Port optional
```

```sh
~/.system1-gateway/engines/laya/start.sh      # LAYA_MODELS / LAYA_PORT env vars optional
```

The launcher binds to `127.0.0.1` (laya-serve's own default is `0.0.0.0`), preloads `typed-decisions`,
uses CUDA or MPS when available and the CPU otherwise, logs to `laya-serve.log` next to it, and does
nothing if the port is already in use. Then point the gateway at it:

```toml
[gateway]
provider = "laya"

[providers.laya]
endpoint = "http://127.0.0.1:8765"
model = "typed-decisions"   # english | multilingual | typed-decisions | "" to let Laya auto-route
```

If laya-serve runs with `LAYA_API_KEY`, set the same value in the `SYSTEM1_LAYA_API_KEY` environment
variable, never in the config file.

## Von

Install `von-sdk` into its own venv, start `von serve --host 127.0.0.1 --port 8777`, and set:

```toml
[gateway]
provider = "von"

[providers.von]
endpoint = "http://127.0.0.1:8777"
model = "von-1.3"
```

## A chat model through Ollama

Pull a model with Ollama (0.12 or later), then name it; `model` is required:

```toml
[gateway]
provider = "ollama"

[providers.ollama]
endpoint = "http://127.0.0.1:11434"
model = "gemma4:e4b"      # see `ollama list`
```

An LLM's letter probabilities are over-confident, so [calibrate](calibrate.md) before you trust a threshold.

## Start at login

The engine does not start on its own, and after a reboot the gateway reports `down` until it does.
`/system1:choose-model` offers a user-level entry, no admin rights needed:

- **Windows:** `system1-laya.cmd` in your Startup folder; `uninstall.ps1` removes it.
- **Linux:** a `systemd --user` unit running `start.sh` (`systemctl --user enable --now system1-laya`).
- **macOS:** a LaunchAgent in `~/Library/LaunchAgents/` running `start.sh` at load.

## Try it without an engine

Set `provider = "mock"` for a deterministic stand-in, or run `python tests/fake_laya.py` from a clone: a fake
that speaks Laya's API on `127.0.0.1:8765`. Both are for checking the plumbing, not for real decisions.
