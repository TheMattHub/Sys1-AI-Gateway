# System-1 Gateway for Claude Code

A local MCP server that gives Claude Code fast, "System-1" decisions from a pluggable decision engine.
Claude Code sees three stable tools. The engines (Laya today; AnyJev or remote APIs later) sit behind
a provider-neutral interface, so you can add or swap one without changing what Claude sees.

- **Stdlib only:** Python 3.11+ and zero third-party dependencies. Installs offline.
- **User-level install:** registered once with `--scope user`, it works in every project. Nothing is added to your projects (no `.mcp.json`).
- **Portable:** a Claude Code plugin with guided setup, or one install script. Works with any MCP client.

```
Claude Code ──stdio/JSON-RPC──▶ server.py ──▶ gateway.py ──▶ providers/laya.py ──HTTP──▶ Laya (local)
(or any MCP client)              3 tools      validate        providers/mock.py
                                              timeout         (future: anyjev.py, remote_api.py …)
                                              threshold / abstain
                                              fallback chain
```

## Quick start: Claude Code plugin (guided setup)

This repo is both a Claude Code plugin (`system1`) and its own marketplace (`system1-gateway`). In Claude Code:

```
/plugin marketplace add <owner>/<repo>        # GitHub, or a local clone path, e.g. C:\src\system1-gateway
/plugin install system1@system1-gateway
/system1:setup
```

### First run

After you install the plugin, the next Claude Code session greets you with a one-line pointer to `/system1:setup`. Then:

| Step | Command | What happens |
|---|---|---|
| 1 | `/system1:setup` | Checks for Python 3.11+, installs the gateway into `~/.system1-gateway/venv`, runs the tests, and registers the `system1` MCP server at user scope |
| 2 | `/system1:choose-model` | Profiles your hardware and preferences, researches current System-1 models, recommends one, and installs it on a yes (Laya: its own venv plus a `start.ps1`/`start.sh` launcher) |
| 3 | (offered by step 2) | Start the engine at login, turn on the model-routing hook, and keep a calibration log |
| 4 | restart Claude Code | Loads the MCP server and the hooks |

Every step asks before changing anything outside the repo. You don't need a clone for this path.

At session start, the plugin stays silent unless something needs you: the gateway isn't installed, the config is broken, or routing is on but the engine isn't running (e.g. after a reboot without start-at-login). In that last case it tells you to start the engine, or to run `/system1:doctor`.

| Skill | Use it to |
|---|---|
| `/system1:setup` | install, upgrade, reconfigure, register or uninstall |
| `/system1:choose-model` | pick the best System-1 engine (Laya, Jev, AnyJev, ...) for your hardware, languages and privacy/cost constraints, using live web research and your Claude memory, then install it on a yes. Engines go in their own venv under `~/.system1-gateway/engines/` |
| `/system1:report` | is System-1 actually used, and does it pay off? Reports reach, hint adherence, subagent cost by tier, realised/missed savings and overhead from your Claude Code transcripts (totals only), then offers a `/system1:calibrate` run with instructions drawn from the findings |
| `/system1:calibrate` | label collected decisions (Claude proposes, you correct), fit the confidence calibration, measure accuracy, set thresholds, and act on the model's known limitations |
| `/system1:doctor` | diagnose a gateway that won't connect, is `down`/`degraded`, times out, returns malformed answers, or always abstains |
| `/system1:add-provider` | add a new engine adapter (AnyJev, a remote API), or update the Laya adapter once its real API is known. Needs a git clone |
| `/system1:toggle on\|off\|status` | pause or resume System-1 everywhere (routing hook, skill picker, `system1_decide`) from the next prompt, with no restart, or show what's on, engine health and today's decisions |

`setup`, `choose-model`, `add-provider` and `toggle` are **user-only**: type the slash command. You start them on purpose, so their descriptions are kept out of every session's context (`disable-model-invocation`). `doctor`, `report` and `calibrate` also trigger from plain words ("why is system1 down?", "is System-1 worth it?"). The plugin adds about 235 tokens to each session (25 of them say when not to use System-1, which saves wasted calls), about $1 per 10,000 model requests at Opus cache-read prices. `toggle` adds none.

**Why the plugin doesn't start the MCP server itself:** a plugin's MCP command is one command line for every OS. On Windows, no single command reliably reaches Python 3.11+: `python3` is often the Microsoft Store stub, `python` may be an older version, and `bash` isn't on PATH. So the plugin carries the skills and the installer. The server is registered at user scope and runs from a pinned venv, which works everywhere and is also what other MCP clients use.

- **Upgrade:** `/plugin marketplace update system1-gateway`, then `/plugin update system1@system1-gateway`, then `/system1:setup` to reinstall.
- **Remove:** `/system1:setup` (uninstall) first, then `/plugin uninstall system1@system1-gateway`.
- **Plugin development:** run `claude --plugin-dir <clone>` to load the plugin straight from a clone.

The skills use [scripts/smoke.py](scripts/smoke.py), which you can also run yourself. It launches the installed gateway exactly as an MCP client does, then checks the handshake, health, and optionally one decision: `<venv python> scripts/smoke.py --question "..." --options a b`.

## Manual install

Requires Python 3.11+ (for `tomllib`).

```powershell
# Windows (PowerShell 5.1+ or 7+)
git clone <this repo> ; cd <repo>
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
```sh
# Linux / macOS
git clone <this repo> && cd <repo>
sh install.sh
```

The script:
1. finds Python ≥ 3.11
2. creates `~/.system1-gateway/venv`
3. **copies** the package into it
4. creates the user config from `config.example.toml` if you don't have one
5. prints the registration command

The installed copy doesn't depend on the clone. Re-run the script to upgrade. To install somewhere else, set `SYSTEM1_INSTALL_DIR`.

## Register with Claude Code

Run the command the installer printed:

```sh
claude mcp add --scope user --transport stdio system1 -- "<venv python>" -I -m system1_gateway
```

- `<venv python>` is `%USERPROFILE%\.system1-gateway\venv\Scripts\python.exe` on Windows, `~/.system1-gateway/venv/bin/python` on Linux/macOS.
- `-I` runs Python in isolated mode, which ignores the project's working directory and `PYTHON*` env vars. Without it, a project file such as `json.py` could shadow the gateway's imports.
- **In PowerShell, quote the separator as `'--'`.** When `claude` is the npm `claude.ps1` shim, PowerShell swallows a bare `--`, and Claude then fails with `unknown option '-I'`. The command `install.ps1` prints is already quoted.

Check it with `claude mcp list`, or `/mcp` inside Claude Code. To remove it: `claude mcp remove --scope user system1`.

## Use with other MCP clients

The gateway is a standard stdio MCP server. Every client launches the same command: the venv Python with `-I -m system1_gateway`. On Windows, JSON configs accept forward slashes: `C:/Users/<you>/.system1-gateway/venv/Scripts/python.exe`.

```json
{ "mcpServers": { "system1": { "command": "<venv python>", "args": ["-I", "-m", "system1_gateway"] } } }
```

| Client | Where it goes |
|---|---|
| Claude Desktop | `claude_desktop_config.json` (Settings → Developer → Edit Config), shape above |
| Cursor | `~/.cursor/mcp.json`, shape above |
| Gemini CLI | `~/.gemini/settings.json`, shape above |
| Windsurf | `~/.codeium/windsurf/mcp_config.json`, shape above |
| VS Code (Copilot) | user `mcp.json` (command *MCP: Open User Configuration*): `{"servers": {"system1": {"type": "stdio", "command": "<venv python>", "args": ["-I", "-m", "system1_gateway"]}}}` |
| Codex CLI | `~/.codex/config.toml`: `[mcp_servers.system1]` with `command = "<venv python>"` and `args = ["-I", "-m", "system1_gateway"]` |

These config locations change between client versions, so check your client's MCP docs if one doesn't work. The skills are Claude Code–only; the tools and their behaviour are the same in every client.

## Configure

Config file: `%APPDATA%\system1\config.toml` (Windows) or `~/.config/system1/config.toml` (Linux/macOS), or any path set in `SYSTEM1_CONFIG`. Every key is optional. Environment variables override the file.

| Key (`[gateway]`) | Default | Env var | Meaning |
|---|---|---|---|
| `provider` | `"laya"` | `SYSTEM1_PROVIDER` | Primary provider |
| `fallback` | `[]` | `SYSTEM1_FALLBACK` (comma list) | Providers tried on failure. Off by default |
| `timeout_s` | `5.0` | `SYSTEM1_TIMEOUT_S` | Limit per provider attempt |
| `min_confidence` | `0.6` | `SYSTEM1_MIN_CONFIDENCE` | Abstain below this. A request can override it |
| `log_level` | `"INFO"` | `SYSTEM1_LOG_LEVEL` | `DEBUG` also logs question text |
| `log_file` | `""` | `SYSTEM1_LOG_FILE` | Logs always go to stderr; set this to also write a file |

Provider settings go in `[providers.<name>]`, or env vars named `SYSTEM1_<NAME>_<KEY>` (e.g. `SYSTEM1_LAYA_ENDPOINT`).

A broken config never stops the server from starting. Instead, `system1_health` reports `down` and `system1_decide` returns `config_error` with the reason.

### Laya

[Laya](https://huggingface.co/convaiinnovations/laya) (Convai, Apache-2.0) runs as its own local server, `laya-serve`, in a separate venv. `/system1:choose-model` installs it into `~/.system1-gateway/engines/laya/`, together with a launcher copied from [engines/laya/](engines/laya/):

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.system1-gateway\engines\laya\start.ps1"   # -Model, -Port optional
```

```sh
~/.system1-gateway/engines/laya/start.sh      # LAYA_MODELS / LAYA_PORT env vars optional
```

The launcher:
- binds to `127.0.0.1` (laya-serve's own default is `0.0.0.0`)
- preloads `typed-decisions`
- uses CUDA/MPS when available, otherwise the CPU
- logs to `laya-serve.log` next to it
- does nothing if the port is already in use

**Start at login** (offered by `/system1:choose-model`):
- Windows: `system1-laya.cmd` in your Startup folder. `uninstall.ps1` removes it.
- Linux: a `systemd --user` unit.
- macOS: a LaunchAgent.

```toml
[providers.laya]
endpoint = "http://127.0.0.1:8765"
model = "typed-decisions"   # english | multilingual | typed-decisions | "" to let Laya auto-route
allow_remote = false        # non-loopback hosts are refused unless true
```

- **Checkpoint pinning:** every request pins `model`. Laya silently auto-routes when it doesn't know a model name, so the adapter rejects any answer whose `routing.model` differs from the pinned one (`malformed_response`).
- **API key:** if laya-serve runs with `LAYA_API_KEY`, set the same value in `SYSTEM1_LAYA_API_KEY`. Only in the environment, never in the config file.
- **Proxy:** local calls bypass any system proxy.

Mapping (all of it in [system1_gateway/providers/laya.py](system1_gateway/providers/laya.py), verified against laya 0.3.20):

| Gateway | laya-serve `POST /v1/systemone` |
|---|---|
| `question` | `questions.decision.instructions` |
| `options` | a `choice` question with `criteria` = options |
| no `options` | a two-option `choice` with `criteria = ["yes", "no"]`, **not** `noul` (see below) |
| `context` | `state` |
| `confidence` | `answer_confidence`, the probability of the returned answer. Laya's own `confidence` is 1 − normalized entropy, a different scale |
| `probabilities` | Laya's per-option `probabilities`. The gateway rescales them when a calibration matches |
| `rationale` | the per-option probabilities, e.g. `laya typed-decisions: block the merge=0.52, rerun the pipeline=0.48` |

Health checks use `GET /health`. The detail warns when the pinned checkpoint isn't preloaded, since the first decision would then be slow.

**Known Laya limitations and how the gateway handles them** (from the [model card](https://huggingface.co/convaiinnovations/laya), checked live on 2026-09-24):

| Limitation | Handling |
|---|---|
| `noul` (yes/no) follows its labels instead of the input. Live, it called `rm -rf`, `DROP TABLE` and a force push "safe" (4/8 right) | Yes/no questions are sent as a two-option choice: 7/8 right in that test, 88% on the 24-command seed set |
| Over- or under-confident until a temperature is fitted | The calibration layer (next section) |
| Close to chance zero-shot on unfamiliar tasks; fine-tuning is Laya's real fix | Measure accuracy with `/system1:calibrate`. Fine-tune with Laya's RLCD notebook once you have a few hundred labeled examples |
| More than ~20 options exhausts the decision head (Banking77: 0.425) | Refused with `provider_error`, so a fallback can take over. Use a coarse-to-fine hierarchy |
| English-only checkpoints are confidently wrong on non-Latin text (95% confidence, 0% right) | The adapter abstains when more than 30% of the letters are non-Latin. Italian and other Latin-script text is unaffected |
| `score` (ordinal) is the weakest question type; `act_probability` is useless | Neither is used |

## Calibration

The provider's probabilities are rescaled with one fitted temperature per (provider, model, question). Questions too rare for their own fit fall back to a fit per option count. This never changes which answer wins; it only makes `confidence`, and so `min_confidence`, mean what it says. Fits come from two places:
1. `~/.system1-gateway/calibration.json`, fitted on this machine. It takes precedence.
2. [system1_gateway/calibration.json](system1_gateway/calibration.json), shipped with the repo, so every install starts calibrated.

A fit for a different model or checkpoint is ignored, and responses carry `"calibrated": true/false`.

**Fits shipped now** (Laya `typed-decisions`, from the teacher-labeled seed sets in [calibration/](calibration/)):

| Question | n | Accuracy | ECE before → after | Temperature | Accuracy at the threshold |
|---|---|---|---|---|---|
| Routing: which Claude model | 45 | 69% | 0.234 → 0.104 | 0.31 (under-confident) | 77% at 0.6 covering 69% of prompts; 82% at 0.75 covering 24% |
| Is this tool call destructive? | 24 | 88% | 0.217 → 0.136 | 0.27 | 94% at 0.75, covering 75% |

**Is it worth it?** `/system1:report` runs [scripts/usage_report.py](scripts/usage_report.py) over your Claude Code transcripts. It shows how often hints appear, whether Claude follows them, and what subagents cost by tier. It estimates realised savings (spawns that followed a hint, repriced at your usual tier mix) and missed savings (spawns upgraded past a hint), minus the hint overhead. Prices come from [scripts/prices.json](scripts/prices.json), API list prices used for comparison; a Claude Code subscription bills differently.

To refit with your own data, run `/system1:calibrate`. It labels the routing log (Claude proposes, you correct), runs [scripts/calibrate.py](scripts/calibrate.py), and applies the fit and threshold. When 30 prompts are waiting to be labeled, the session-start hook suggests it. These numbers are measured on the same data they were fitted on and come from small samples, so treat them as rough.

To try the gateway without Laya, run `python tests/fake_laya.py` (a fake speaking the same API on 127.0.0.1:8765), or set `provider = "mock"`.

## Tools (schema v1)

**`system1_decide`**:

| Field | Required | Notes |
|---|---|---|
| `question` | yes | ≤ 8000 characters |
| `options` | no | 2–50 unique strings; the decision must be one of them |
| `context` | no | object, passed to the provider |
| `min_confidence` | no | 0–1, overrides the configured threshold |
| `request_id` | no | echoed back; generated if omitted |
| `schema_version` | no | `"1"` |

Unknown fields are rejected.

Response:
```json
{"schema_version": "1", "request_id": "…", "status": "decided | abstained | error",
 "decision": "…", "confidence": 0.93, "rationale": "…", "provider": "laya", "latency_ms": 12,
 "attempts": [{"provider": "laya", "outcome": "ok", "latency_ms": 12, "detail": null}],
 "error": null}
```
Error codes: `invalid_request`, `config_error`, `provider_timeout`, `provider_error`, `malformed_response`.

**`system1_health`**: returns `ok`, `degraded` (primary down, a fallback up) or `down`, with a probe result for each provider.
**`system1_capabilities`**: returns the version, schema versions, provider chain, thresholds and the full request/response JSON Schemas.

### Behaviour
- **Validation on both sides:** requests are checked before any provider runs. Provider answers are checked by the gateway, not the adapter: non-object, confidence outside [0, 1], or a decision not in `options` → `malformed_response`.
- **Abstention:** if the provider abstains, or its confidence is below the threshold, the status is `abstained` and `decision` is `null`. That's a valid answer meaning "reason it through yourself". **It does not trigger a fallback.**
- **Fallback:** runs only on `timeout`, `error` or `malformed`, trying providers in order. Every try is recorded in `attempts`.
- **Timeouts** apply to each attempt. A Python thread can't be killed, so adapters must also pass the timeout to their own I/O.
- **Logs** go to stderr, since stdout is reserved for the protocol. Every line is tagged with the request id.

## Model-routing hook (Claude Code plugin)

A System-1 model can't be a chat or subagent model, because it doesn't write text or call tools. It can help decide *which* Claude model should. On every prompt, the plugin's `UserPromptSubmit` hook ([hooks/hooks.json](hooks/hooks.json) → [route_hook.py](system1_gateway/route_hook.py)) asks the configured provider four yes/no questions about what the text shows: `read_only`, `design`, `review` and `specified` ([routing_features.py](system1_gateway/routing_features.py)). They're answered in one engine pass. A small rule that you own, [routing_rule.py](system1_gateway/routing_rule.py), turns the answers into **haiku**, **sonnet** or **opus**. When hints are on and every answer clears the threshold, the hook adds a hint to Claude's context, and Claude uses it as the `model` for subagents it spawns.

**Why features, not "which model?":** asked directly, every engine failed on 284 labeled tasks. Laya scored 46–54%, Von 57% and Gemma 4 E4B 62%, against 52% for always answering "sonnet". Judging how hard a task is takes reasoning. A decision model is good at properties you can read off the text, so that's what it's asked, and the policy stays yours.

```toml
[routing]
enabled = true                                   # off by default
log_dirs = ["~/src/my-project"]                  # calibration log: only prompts from these repos (default: none)
hint = false                                     # log only, no hint (while collecting labels)
```

- **Advisory only:** the hook never blocks or rewrites a prompt.
- **Silent** when the provider abstains, fails, or isn't installed, for slash commands and prompts under 10 words, and for subagent hand-backs (`<agent-message>`, `<task-notification>`), which are reports rather than tasks.
- **Cost:** about 0.5 s per prompt with Laya warm on a GPU, mostly Python startup. It's capped at 1.5 s when the engine is down.
- **Log:** off by default, and **opt-in per repo**. A prompt is logged only when Claude Code's working directory is one of `log_dirs` or inside one, so confidential repos stay out unless you list them. Each entry in `~/.system1-gateway/logs/routing.jsonl` keeps the repo path, the prompt text (locally), the four feature answers with their confidence (`features`), and the rule's tier (`rule_tier`, also in `decision`).
- **Agent spawns (record-only):** a PreToolUse hook on the Agent tool logs the same for each subagent brief, next to the model the orchestrator chose (`"source": "agent"`, `chosen`, `subagent_type`, `tool_use_id`). It prints nothing and never changes the spawn. `/system1:report` summarises these entries under *shadow*.
- **Hints stay off** (`hint = false`) until `scripts/evaluate.py` says READY (see [Is an engine ready?](#is-an-engine-ready)). `[routing] min_confidence` sets routing's own threshold.
- **Short prompts:** under 10 words a prompt is usually a follow-up ("Plan is ok, implement") whose size depends on the conversation, which the hook can't see. Those were 0/3 right, so Claude decides them unaided and no engine call is made.
- **Debugging:** the hook hides its own errors. Run `<venv python> -I -m system1_gateway.route_hook` and paste `{"prompt": "..."}` to see what it does.

Works in Claude Code only (hooks are specific to that harness). Other MCP clients use the tools.

### Outcome labels

The orchestrator's model choice isn't a correct label; whether that model got the job done is. [scripts/outcomes.py](scripts/outcomes.py) reads the transcripts and proposes an outcome for every Agent spawn:
- **failed:** the tool result was an error; the task notification's status was `failed` or `stopped`; the report says the agent was blocked; or a later spawn redid the same task. A redo means the same primary task id (`W4-P3`, `Task 12`) plus "previous attempt"/"retry", or a same-role re-spawn of it.
- **succeeded:** otherwise.

The tier is the model that actually ran (`resolvedModel`), which also covers `inherit`. `--apply` writes `outcome`, `outcome_reason`, `outcome_tier` and `outcome_source: "auto"` into the log. `/system1:calibrate` then asks you only about the doubtful ones. On 30 days of transcripts (2026-09-30), 279 spawns gave 25 failures, 4 of them doubtful. The script prints counts plus the doubtful list, locally.

### Is an engine ready?

```sh
<venv python> scripts/evaluate.py --provider laya     # or von, ollama; one engine at a time on a small GPU
```

It's read-only. It asks the engine the four features for every log entry with feature labels or an outcome, and reports:
- **Per feature:** accuracy, AUROC, and coverage and accuracy at the routing threshold, against the teacher feature labels.
- **The rule:** on outcome-labeled spawns, *safety* is the share of failures where the rule would have picked a higher tier; *agreement* and *savings* cover the successes. It's shown with the engine's answers and with the teacher labels (the rule's ceiling), so a weak rule and a weak engine can be told apart.
- **Verdict:** `READY` only if every feature is at least 85% accurate at the threshold, safety is at least 95%, and at least 30 failed spawns are labeled. Change the bars with `--min-feature-accuracy`, `--min-safety` and `--min-failures`.

### Engines

| Provider | Engine | Start it | Notes |
|---|---|---|---|
| `laya` | Laya `typed-decisions` | `~/.system1-gateway/engines/laya/start.ps1` | one pass for all four features; at most 20 options |
| `von` | Von 1.3 (`pip install von-sdk`) | `von serve --host 127.0.0.1 --port 8777` | one pass; 8,192-token context; no option limit |
| `ollama` | any local chat model | Ollama (≥ 0.12, for logprobs) | one call per feature (four per prompt), so it's usually too slow for the hook, but fine for `evaluate.py` |

```toml
[providers.von]
endpoint = "http://127.0.0.1:8777"
model = "von-1.3"

[providers.ollama]
endpoint = "http://127.0.0.1:11434"
model = "gemma4:e4b"      # see `ollama list`
```

### Skill picker

The same hook can ask System-1 which skill fits the prompt, and add a one-line hint (``consider the `x` skill if it fits``). The candidates are the skills Claude can load, taken from the hook input when Claude Code sends a list, otherwise from `~/.claude/skills`, the project's `.claude/skills` and every enabled plugin's `skills/`. Skills with `disable-model-invocation: true` are left out.

```toml
[skills]
enabled = true          # off by default (SYSTEM1_SKILLS_ENABLED)
hint = false            # record-only by default: logs to routing.jsonl with "source": "skill" (SYSTEM1_SKILLS_HINT)
min_confidence = 0.8    # above routing's bar: a wrong skill load costs a whole skill body (SYSTEM1_SKILLS_MIN_CONFIDENCE)
```

- **Dormant until the engine can take it:** a typical setup has about 100 loadable skills. Laya's decision head handles at most 20 options, so with Laya the picker makes no engine call and costs nothing. It wakes on its own for a provider whose `max_options` holds the whole list (the request schema allows up to 256).
- **One budget:** routing and the picker share the hook's 1.5 s engine budget. If routing uses it up, the picker is skipped.

## Add a provider (e.g. AnyJev)

1. Create `system1_gateway/providers/anyjev.py` with a subclass of `System1Provider` (see [base.py](system1_gateway/providers/base.py)):
   - `decide(request, timeout_s)` returns `{"decision", "confidence", "rationale"}` or `{"abstain": True}`.
   - `health(timeout_s)` returns `{"ok", "detail"}`.
   - The constructor raises `ValueError` if the settings are unusable.
2. Add `"anyjev": AnyJevProvider` to `REGISTRY` in [providers/__init__.py](system1_gateway/providers/__init__.py).
3. Configure it with `provider = "anyjev"` or `fallback = ["anyjev"]`, then re-run the installer.

The MCP tools and schemas stay the same.

## Tests

```sh
python -m unittest discover -s tests -v     # from the repo root, Python 3.11+
```

The tests cover:
- schema validation
- provider selection
- config and env overrides
- malformed responses
- timeouts
- fallback and abstention
- the Laya adapter against a local fake server
- an end-to-end stdio JSON-RPC session

They make no network calls beyond 127.0.0.1.

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1          # add -Purge to delete the config too
```
```sh
sh uninstall.sh                                                   # add --purge to delete the config too
```

Uninstalling:
- unregisters the MCP server (if `claude` is on PATH)
- deletes `~/.system1-gateway/venv`
- removes the Windows start-at-login entry

Your config, the engines (Laya is about 6 GB) and the logs are kept unless you pass `-Purge`/`--purge`. Stop the engine before purging, because Windows can't delete a running `laya-serve.exe`.

## Releases

Tags follow the plugin convention `system1--v<version>` (`claude plugin tag . --push`). Each release also gets a one-word codename, in alphabetical order, taken from Kahneman's *Thinking, Fast and Slow*:
- **Minor and patch releases** take the next letter.
- **Major releases** break the alphabet and take the authors' names.

| Release | Codename | Concept |
|---|---|---|
| 0.1.9 | **Anchoring** | An initial number drags every later estimate toward it. The routing hint anchors Claude's model choice |
| 0.1.10 | **Baserate** | Base-rate neglect: a vivid story beats the statistics. Routing now gathers its own base rate, silently, before trusting the hint |
| 0.1.11 | **Coherence** | System 1 builds the most coherent story, not the most likely one. Routing stays out of follow-ups it can't see the story for, and the skill picker waits for an engine that can hold the whole list |
| 0.1.12 | **Denominator** | Denominator neglect: "1 in 10" feels riskier than "10%". Routing is now judged on outcome counts, not on how sure the engine sounds |
| next | **Econs** | The perfectly rational agents of economics, as opposed to Humans |
| | **Framing** | The same facts described differently lead to different choices |
| | **Halo** | Liking one trait colors judgment of all the others |
| | **Illusion** | The illusion of validity: confidence without accuracy, which is exactly what calibration corrects |
| 1.0 | **Kahneman** | |
| 2.0 | **Tversky** | Amos Tversky, Kahneman's research partner behind heuristics and prospect theory |
