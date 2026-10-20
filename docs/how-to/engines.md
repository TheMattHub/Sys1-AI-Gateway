# Install an engine

An engine is the local model that actually answers; the gateway only talks to it. The easiest path is
`/system1:choose-model`: it profiles your hardware and preferences, checks the current models online,
recommends one checkpoint and installs it on a yes, each engine in its own venv under
`~/.system1-gateway/engines/`. This page shows what it sets up, for when you want to do it by hand.

Which engine to pick is a question of speed, accuracy and hardware, measured in the
[naga decisions study](../studies/naga-decisions.md). The gateway has adapters for every engine the study
recommends:

| Provider | Engine | Start it | Notes |
|---|---|---|---|
| `laya` | Laya `typed-decisions` | `~/.system1-gateway/engines/laya/start.ps1` or `start.sh` | one pass for several questions; at most 20 options |
| `von` | Von 1.3 (`pip install von-sdk`) | `von serve --host 127.0.0.1 --port 8777` | one pass; 8,192-token context; no option limit declared |
| `ollama` | any local chat model | Ollama 0.12 or later (for logprobs) | one call per question; at most 26 options |
| `systemone` | Liquid AI d1 through llama.cpp, or a Hugging Face-only engine through [engines/systemone/serve.py](../../engines/systemone/serve.py) (gte reranker, Qwen3-Reranker, AnyJev, OpenThai-SystemOne) | `llama-server -m <model>.gguf --port 8790 ...` or `python engines/systemone/serve.py --engine gte` | the same `/v1/systemone` contract as Von |
| `anthropic` | a hosted Claude model (default Claude Haiku 5.5) | nothing to start; needs `ANTHROPIC_API_KEY` | requests leave your machine and are billed per token |

For any other engine, see [Add a provider](add-provider.md).

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

## A decision model through llama.cpp (Liquid AI d1)

llama.cpp's `llama-server` serves native decision models such as Liquid AI's d1 at `POST /v1/systemone`
(build b11757 or later). Download a GGUF (for example `LiquidAI/d1-3B-GGUF`, file `d1-3B-Q8_0.gguf`, which fits a
4 GB GPU), and start it on loopback with one slot and a batch that holds the whole input:

```sh
llama-server -m d1-3B-Q8_0.gguf --host 127.0.0.1 --port 8790 -ngl 99 -np 1 -c 16384 -b 16384 -ub 16384
```

```toml
[gateway]
provider = "systemone"

[providers.systemone]
endpoint = "http://127.0.0.1:8790"
```

The d1 models carry the LFM Open License v1.0, which licenses commercial use only below USD 10 M annual revenue.

## A Hugging Face-only engine

The gte reranker, Qwen3-Reranker, AnyJev and OpenThai-SystemOne ship as Python weights with no server of their own.
[engines/systemone/serve.py](../../engines/systemone/serve.py) wraps one of them in the same `/v1/systemone`
contract on `127.0.0.1:8790`, so the `systemone` provider above reaches it unchanged. Run it in its own venv with
`torch` and `transformers` (plus `sentence-transformers` for gte, `anyjev` and `bitsandbytes` for AnyJev,
`openthai-systemone` for OpenThai):

```sh
python engines/systemone/serve.py --engine gte     # gte | qwen3-rerank | anyjev | openthai; --model, --port optional
```

The server binds `127.0.0.1` only and refuses requests whose `Host` is not `127.0.0.1` or `localhost` on its port,
bodies that are not JSON or over 1 MB, and more than 16 questions or 256 options, so a web page in your browser
cannot drive it. Set `SYSTEM1_SYSTEMONE_API_KEY` in both the server's and the gateway's environment to require a
bearer token too. The provider sends each option as its own description, so a reranker scores the option text alone; options
that say what they mean ("billing: charges, refunds") work much better than bare names.

## A hosted Claude model

The `anthropic` provider calls the Anthropic Messages API over HTTPS and reads the key from the
`ANTHROPIC_API_KEY` environment variable, never from the config file:

```toml
[gateway]
provider = "anthropic"

[providers.anthropic]
model = "claude-haiku-5-5"
```

It was the most accurate engine in the study, but every request leaves your machine, needs a network and is
billed per token. The API gives no answer probabilities, so `confidence` is the model's own estimate and the
calibration layer cannot rescale it.

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
Decision models built for Ollama's own System One endpoint may do worse through this letter prompt: the Ollama
build of OpenThai-SystemOne got 5 of 40 block questions this way, against 23 through its own client.

## Start at login

The engine does not start on its own, and after a reboot the gateway reports `down` until it does.
`/system1:choose-model` offers a user-level entry, no admin rights needed:

- **Windows:** `system1-laya.cmd` in your Startup folder; `uninstall.ps1` removes it.
- **Linux:** a `systemd --user` unit running `start.sh` (`systemctl --user enable --now system1-laya`).
- **macOS:** a LaunchAgent in `~/Library/LaunchAgents/` running `start.sh` at load.

## Try it without an engine

Set `provider = "mock"` for a deterministic stand-in, or run `python tests/fake_laya.py` from a clone: a fake
that speaks Laya's API on `127.0.0.1:8765`. Both are for checking the plumbing, not for real decisions.
