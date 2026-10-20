# Slash commands and scripts

The plugin adds seven slash commands to Claude Code, and each one drives scripts that you can also run
yourself with the gateway venv Python. The scripts are in [scripts/](../../scripts/) and run from a clone
or from the plugin copy.

## Slash commands

| Command | Use it to |
|---|---|
| `/system1:setup` | install, upgrade, reconfigure, register or uninstall |
| `/system1:choose-model` | pick an engine for your hardware, languages and privacy or cost constraints, using live web research and your Claude memory, then install it on a yes |
| `/system1:report` | see whether System-1 is used and pays off: reach, hint adherence, subagent cost by tier, realised and missed savings, overhead (totals only); then offer a focused calibration |
| `/system1:calibrate` | label collected decisions, fit the calibration, measure accuracy and set thresholds |
| `/system1:doctor` | diagnose a gateway that will not connect, is `down` or `degraded`, times out, answers malformed or always abstains |
| `/system1:add-provider` | add or update an engine adapter; needs a git clone |
| `/system1:toggle on\|off\|status` | pause or resume System-1 everywhere from the next prompt, with no restart, or show its state |

`setup`, `choose-model`, `add-provider` and `toggle` are user-only: you type them, so their descriptions stay
out of every session's context. `doctor`, `report` and `calibrate` also trigger from plain words ("why is
system1 down?", "is System-1 worth it?").

## Scripts

| Script | What it does |
|---|---|
| `smoke.py [--python PATH] [--question Q --options A B ...]` | starts the installed gateway as an MCP client does; checks the handshake, health and optionally one decision. Exit 0 when all pass |
| `toggle.py on\|off\|status` | pauses or resumes System-1 (a pause file), or shows its state |
| `calibrate.py DATA.jsonl [--target-accuracy 0.8] [--write \| --ship] [--json]` | fits a temperature per question from labelled decisions and reports accuracy, ECE, AUROC and a threshold table |
| `evaluate.py [--provider NAME] [--log PATH] [--min-feature-accuracy 0.85] [--min-safety 0.95] [--min-failures 30] [--json]` | read-only: is an engine ready to route? Verdict `READY` or `NOT READY` |
| `outcomes.py [--days 30] [--projects-dir DIR] [--apply] [--json]` | proposes `failed` or `succeeded` for every Agent spawn from your transcripts; `--apply` writes it into the routing log |
| `usage_report.py [--days 14] [--projects-dir DIR] [--prices FILE] [--json]` | read-only: how often hints appear, adherence, subagent cost by tier and estimated savings, from your transcripts |

The transcript readers print aggregates only, never prompt text. Costs come from
[scripts/prices.json](../../scripts/prices.json), API list prices used to compare tiers; a Claude Code
subscription bills differently.

## Install scripts

| Script | What it does |
|---|---|
| `install.ps1`, `install.sh` | create or reuse `~/.system1-gateway/venv`, copy the package in, create the config if missing, print the registration command |
| `uninstall.ps1 [-Purge]`, `uninstall.sh [--purge]` | unregister, delete the venv and the Windows login entry; `-Purge` also deletes config, engines and logs |

## Tests

```sh
python -m unittest discover -s tests -v     # from the repo root, Python 3.11+
```

The tests cover schema validation, provider selection, config and environment overrides, malformed
responses, timeouts, fallback and abstention, the adapters against local fake servers, the hooks, the
scripts, and an end-to-end stdio JSON-RPC session. They make no network calls beyond 127.0.0.1.
