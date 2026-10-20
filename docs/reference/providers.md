# Providers

A provider is the adapter between the gateway and one engine, and six are built in: `laya`, `von`,
`systemone`, `ollama`, `anthropic` and `mock`. Each reads its settings from `[providers.<name>]` or from `SYSTEM1_<NAME>_<KEY>`
environment variables, and every HTTP adapter refuses a non-loopback endpoint unless `allow_remote = true`
and bypasses any system proxy for local calls. To add another, see [Add a provider](../how-to/add-provider.md).

| Provider | Settings (default) | Options | Several questions in one pass |
|---|---|---|---|
| `laya` | `endpoint` (`http://127.0.0.1:8765`), `model` (`typed-decisions`), `allow_remote` (`false`), `api_key` (env only) | at most 20 | yes |
| `von` | `endpoint` (`http://127.0.0.1:8777`), `model` (`von-1.3`), `allow_remote`, `api_key` (env only) | no declared limit | yes |
| `systemone` | `endpoint` (`http://127.0.0.1:8790`), `model` (unset: not sent), `allow_remote`, `api_key` (env only) | the server's (llama-server: 255) | yes |
| `ollama` | `endpoint` (`http://127.0.0.1:11434`), `model` (required), `allow_remote` | at most 26 | no, one call per question |
| `anthropic` | `endpoint` (`https://api.anthropic.com`), `model` (`claude-haiku-5-5`); key from `ANTHROPIC_API_KEY` only | the schema's 256 | no, one call per question |
| `mock` | `confidence` (`0.9`), `delay_s` (`0`), `fail`, `response`, `max_options` | any | no |

## laya

The adapter talks to `laya-serve`, `POST /v1/systemone`, and was verified against laya 0.3.20; health uses
`GET /health`, and its detail warns when the pinned checkpoint is not preloaded. Every request pins `model`:
Laya silently auto-routes an unknown model name, so an answer from another checkpoint is rejected as
`malformed_response`. Set `model = ""` to let Laya route on purpose.

| Gateway | laya-serve |
|---|---|
| `question` | `questions.decision.instructions` |
| `options` | a `choice` question with `criteria` = options |
| no `options` | a two-option `choice` with `criteria = ["yes", "no"]`, not Laya's `noul` (see below) |
| `context` | `state` |
| `confidence` | `answer_confidence`, the probability of the returned answer (Laya's own `confidence` is a different scale) |
| `probabilities` | Laya's per-option `probabilities`, rescaled when a calibration matches |
| `rationale` | the per-option probabilities, e.g. `laya typed-decisions: block the merge=0.52, rerun the pipeline=0.48` |

Known Laya limitations and how the adapter handles them (from the
[model card](https://huggingface.co/convaiinnovations/laya), checked live on 2026-09-24):

| Limitation | Handling |
|---|---|
| `noul` (yes/no) follows its labels instead of the input; live, it called `rm -rf`, `DROP TABLE` and a force push "safe" (4/8 right) | yes/no questions go as a two-option choice: 7/8 right in that test, 88% on the 24-command seed set |
| over- or under-confident until a temperature is fitted | the calibration layer |
| close to chance zero-shot on unfamiliar tasks | measure with `/system1:calibrate`; fine-tune once you have a few hundred labelled examples |
| more than about 20 options exhausts the decision head | refused with `provider_error`, so a fallback can take over; use a coarse-to-fine hierarchy |
| English-only checkpoints are confidently wrong on non-Latin text | abstains when more than 30% of the letters are non-Latin; use `model = "multilingual"` for such text |
| `score` (ordinal) is the weakest question type | not used |

## von

The adapter talks to `von serve`, `POST /v1/systemone`, verified against von-sdk 1.3.1. Options are sent as
a `{option: option}` criteria map, and `confidence` is the probability of the chosen option, since Von's own
`confidence` is another scale. Von reads an 8,192-token window.

## systemone

The Von contract for any other server that speaks it: llama.cpp's `llama-server` with a native decision model
(Liquid AI d1, verified against build b11757 on 2026-10-21) or [engines/systemone/serve.py](../../engines/systemone/serve.py)
for the Hugging Face-only engines. Requests and answers map as for `von`; `model` is sent only when set, since
llama-server answers with the model it loaded. Health is `GET /health`.

## ollama

Any local chat model with logprobs (Ollama 0.12 or later), through `POST /api/chat`. Options are shown as
letters and the model answers one letter at temperature 0; the probabilities are the letters' shares of the
top logprobs. A reply that is not an option letter is `malformed_response`. Health checks that `model` is
installed. An LLM's letter probabilities are over-confident, so calibrate before trusting a threshold.

## anthropic

A hosted Claude model through the Messages API, `POST /v1/messages`, with `urllib` (no SDK). The options go in a
cached system block and the model answers through one forced tool call, `choose`, with up to three option names
best first and a `confidence`. That confidence is the model's own estimate, since the API returns no answer
probabilities, so there are no `probabilities` and no calibration applies. The key is read from the
`ANTHROPIC_API_KEY` environment variable on every call and never logged or put in an error; the endpoint must be
https (plain http only on loopback). Health is `GET /v1/models/{model}`. Every request leaves the machine and is
billed per token.

## mock

A deterministic stand-in for tests and for trying the gateway: it always picks the first option with the
configured `confidence`, sleeps `delay_s`, raises a provider error with the text of `fail`, or returns
`response` verbatim (for malformed-response tests).
