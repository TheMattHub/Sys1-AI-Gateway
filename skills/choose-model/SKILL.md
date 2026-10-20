---
name: choose-model
disable-model-invocation: true
description: Research and recommend the best System-1 decision model for this machine and user, then install it on a yes.
---

# Choose a System-1 model

Goal: one evidence-based recommendation that fits this user's hardware, languages, privacy and cost constraints, followed by a yes/no offer to install it. This field moves fast. **Never recommend from memory alone. Verify online first**, and say so when a source is newer than your knowledge.

Gateway root (holds `system1_gateway/`, `scripts/`): two directories above this skill's base directory.

## 1. Profile the user (read-only, no questions yet)
- **Hardware:**
  - Windows: `Get-CimInstance Win32_ComputerSystem` (RAM), `Win32_Processor`, `Win32_VideoController`, `nvidia-smi --query-gpu=name,memory.total --format=csv`.
  - macOS: `sysctl hw.memsize machdep.cpu.brand_string`, `system_profiler SPDisplaysDataType`.
  - Linux: `free -g`, `lscpu`, `nvidia-smi`.
  - Note GPU VRAM (NVIDIA → CUDA; Apple Silicon → MPS), free disk space, and installed Python versions.
- **Memory:** read every `~/.claude/projects/*/memory/MEMORY.md` index, then open only the entries of type `user` or `feedback`, or those relevant to cost, privacy, languages or domain. Look for:
  - bans on paid APIs, and preferences for local tools
  - confidential clients or data (these rule out hosted models)
  - working languages (non-English → multilingual checkpoint)
  - the domain of the decisions (triage, routing, guardrails, code-review gates, ...)
- **Current setup:** the user config (`provider`, `fallback`, `[providers.*]`), `REGISTRY` in `system1_gateway/providers/__init__.py` (which adapters already exist), and anything already under `~/.system1-gateway/engines/`.
- **This session:** what the user has said about their use cases.

Summarize the profile in 3–5 lines. Ask the user (AskUserQuestion) **only** about gaps that would change the pick. For example, whether decision inputs are in languages other than English.

## 2. Research candidates online
- Use WebSearch for the current landscape: `"System One" decision model`, `Jev-compatible model`, `Laya decision model`, `AnyJev`, the `awesome-jev` list, plus anything newer they point to.
- As of 2026-09 the known candidates were:
  - **Laya** (Convai): open, Apache-2.0, ~421M params, local, `laya-serve` exposes the Jev-compatible `POST /v1/systemone`.
  - **Jev** (TypeSafe AI): closed, hosted, paid, waitlisted.
  - **AnyJev** (Nokia): a training-free layer over open LLMs, `transformers` only, no HTTP server.
  - Community reproductions.

  Re-check all of them; versions, licenses and checkpoints change.
- **Read primary sources for every finalist:** the Hugging Face model card, the GitHub README, the official docs. Extract:
  - license
  - open or closed weights
  - price
  - size and memory footprint
  - latency on CPU and GPU
  - languages
  - context length
  - accuracy per checkpoint (base vs fine-tuned often differ a lot)
  - calibration notes
  - serving method (HTTP server? which API?)
  - install command and Python version
- **Trust:** download only from the official Hugging Face org, PyPI package or GitHub repo named on the model card. Flag look-alike "download" sites and don't use them. When secondary sources contradict primary ones, trust the primary and say so.

## 3. Decide
Hard filters come first:
- **Hosted/paid models are out** if memory or the user bans paid APIs or has confidential data.
- **Size must fit:** the model plus runtime must fit in VRAM (for GPU speed) or RAM (for CPU).

Then rank the survivors on:
1. accuracy for the user's decision types
2. calibration (the gateway's `min_confidence` depends on it)
3. latency
4. how well it fits the gateway: an existing adapter, or a stable HTTP API that one adapter file can map
5. setup and maintenance effort

Pick **one model and one specific checkpoint**, plus a runner-up.

## 4. Present
- **The recommendation:** model + checkpoint, then one line on why it fits *this* user.
- **A comparison table** of the finalists, covering the fields from step 2.
- **What installing means:**
  - disk space and download size
  - the separate venv path
  - how the engine is started
  - whether the gateway adapter already matches its API, or needs `/system1:add-provider` (compare against the adapter's documented contract)
  - the need for temperature calibration if the card says it's over-confident
- **Sources** as markdown links.

## 5. Ask yes/no to install
Use AskUserQuestion: **"Install <model> (<checkpoint>) now?"** with two options, *Yes, install it* and *No, not now*.
- **Hosted/closed model** (nothing to install locally): don't offer an install. Offer to add an adapter via `/system1:add-provider` instead. Credentials go only in env vars (`SYSTEM1_<NAME>_API_KEY`), and the endpoint needs `allow_remote = true` with the user's explicit OK.
- **No:** stop there. The recommendation stands for later.

## 6. Install (only after "Yes")
Engines get their **own** venv. Never install them into the gateway venv, which is stdlib-only by design.
1. Find a Python that meets the engine's minimum version (on Windows prefer `py -3.12`; bare `python` may be old or the Microsoft Store stub). Create `~/.system1-gateway/engines/<model>/venv`.
2. **GPU:** install the matching accelerated framework first, e.g. PyTorch with CUDA from the official index for the detected driver, then the engine using the command from its official docs (e.g. `pip install "laya[serve]"`). CPU-only machines skip the CUDA step.
3. Download the chosen checkpoint and print its disk footprint.
4. **Launcher:** if the gateway root has `engines/<model>/` (Laya: `start.ps1`, `start.sh`), copy those files into `~/.system1-gateway/engines/<model>/`. The plugin copy moves on every update, so never point anything at it. Start the engine through the launcher, in the background. It binds to loopback and logs to `laya-serve.log` in the engine folder. For engines with no launcher, start the server directly on loopback (e.g. `127.0.0.1:8765`) with the chosen checkpoint. **Probe it with a real request built from its documented API**, and save one raw request/response pair for the adapter work. For Laya, `LAYA_MODELS` takes the short name (`typed-decisions`), and each request must pin `"model"`, because unknown names are silently auto-routed.
5. **Wire the gateway:**
   - If the adapter's contract matches the live API, set `[providers.<name>] endpoint` in the user config (show the diff) and run `<gateway venv python> scripts/smoke.py --question ... --options ...`.
   - If it doesn't match (e.g. a Laya release that changed its API), say so and ask the user to run `/system1:add-provider` (user-invoked), pointing it at the saved request/response pair.
6. **Offer the follow-ups** in one AskUserQuestion (`multiSelect: true`). Apply only what the user picks, and show config diffs first.
   - **Start at login.** The engine doesn't start on its own, and after a reboot the gateway is `down` until it does.
     - Windows: create `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\system1-laya.cmd` containing
       `@start "" /min powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "<engine folder>\start.ps1"`.
     - Linux: a `systemd --user` unit running `start.sh` (`systemctl --user enable --now system1-laya`).
     - macOS: a LaunchAgent in `~/Library/LaunchAgents/` running `start.sh` at load.
     - All three are user-level; no admin rights needed. The uninstall scripts remove the Windows entry. Tell Linux/macOS users how to remove theirs.
   - **Model-routing hook:** `[routing] enabled = true`, so the plugin suggests haiku/sonnet/opus for subagents on each prompt. Say that until calibration it will usually stay silent, because confidence stays below the threshold.
   - **Calibration log, per repo:** `[routing] log_dirs = [...]`. It's off by default, and prompts are logged only from the listed folders. Ask which repos to include, and suggest leaving out any that hold confidential or client work (check memory for those). The log keeps prompt text on this machine, in `~/.system1-gateway/logs/routing.jsonl`.
7. **Calibrate:** explain that `min_confidence` is only meaningful once a calibration matches the installed provider and checkpoint. The repo ships fits for Laya `typed-decisions`. For any other model, or to refit on the user's own prompts, hand over to `/system1:calibrate`.
8. **Report:**
   - install path and disk used
   - the start command (the launcher), and whether it starts at login
   - the smoke result
   - what's left to do

Ask before anything outside the engine folder: editing the user config, changing env vars, or installing system packages or drivers. Never commit anything.
