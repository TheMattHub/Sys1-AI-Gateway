# What System-1 means here

The name comes from Daniel Kahneman's *Thinking, Fast and Slow*: System 1 is fast and intuitive, System 2
slow and deliberate. Here a System-1 model is a small model that answers a multiple-choice question in tens
or hundreds of milliseconds, without writing text, and Claude is System 2. The gateway lets Claude hand the
small judgement calls to the fast model and keep the reasoning for itself.

## What it is for, and what it is not

A System-1 model is good at properties you can read off the text: which of these tools fits the request,
is this command destructive, does this task only look something up. It is not for writing, chat,
multi-step reasoning, counting, maths or dates; Claude does those itself and asks System-1 only the
judgement call. It cannot be a chat or subagent model either, because it does not write text or call
tools, but it can help decide which Claude model should ([model routing](../how-to/routing.md)).

## Why it abstains

A fast answer is only useful when you know how far to trust it. Every answer carries a confidence, and
below the threshold the gateway returns `abstained` instead of a guess, which tells Claude to reason it
through. For the threshold to mean what it says, the engine's probabilities are calibrated on labelled
decisions ([How routing and calibration work](routing-and-calibration.md)).

## Why one gateway in front of many engines

This field moves fast, so the engine should be easy to swap. Claude sees three stable tools, and the engines
sit behind a provider-neutral interface; adding or changing one changes one adapter file, not what Claude
sees. Which engine to pick is measured, not assumed: see the
[naga decisions study](../studies/naga-decisions.md).

```
Claude Code ──stdio/JSON-RPC──▶ server.py ──▶ gateway.py ──▶ providers/laya.py ──HTTP──▶ Laya (local)
(or any MCP client)              3 tools      validate        providers/von.py, ollama.py, mock.py
                                              timeout         (or your own)
                                              threshold / abstain
                                              fallback chain
```

## Design choices

- **Stdlib only:** Python 3.11+ and no third-party dependencies, so it installs offline. Engines get their
  own venvs.
- **User-level:** registered once with `--scope user`, it works in every project and adds nothing to them.
- **Small context cost:** the plugin adds about 235 tokens to each session (25 of them say when not to use
  System-1, which saves wasted calls), about $1 per 10,000 model requests at Opus cache-read prices.
- **The plugin does not start the server itself:** a plugin's MCP command is one command line for every OS,
  and on Windows no single command reliably reaches Python 3.11+ (`python3` is often the Microsoft Store
  stub, `python` may be older, `bash` is not on PATH). So the plugin carries the skills and the installer,
  and the server runs from a pinned venv registered at user scope, which also serves other MCP clients.
