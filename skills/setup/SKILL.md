---
name: setup
disable-model-invocation: true
description: Guided install, upgrade, registration or uninstall of the System-1 gateway.
---

# System-1 gateway setup

Walk the user through setup one step at a time. Report each result before moving on, and stop at the first failure with its output.

**Gateway root** (the folder holding `install.ps1`, `install.sh`, `system1_gateway/`, `scripts/`, `tests/`): two directories above this skill's base directory. That's the plugin's bundled copy of the repo, or the git clone when run with `--plugin-dir`. Run every script below from there. You never need to clone: the installer copies the package into a user-level venv, so plugin updates and cache moves don't affect the installed gateway.

## Ground rules
- Everything is user-level: the venv in `~/.system1-gateway`, the user config file, and `claude mcp` with `--scope user`. Never create `.mcp.json` or project-scope registrations, and never touch other projects.
- **Ask before** you register or unregister with Claude Code, `git pull`, uninstall, or edit the user config. Don't commit anything.
- Never write secrets into the config file or the repo. Credentials go in env vars (`SYSTEM1_<PROVIDER>_<KEY>`).
- Shell: on Windows use PowerShell with `install.ps1`/`uninstall.ps1`. On Linux/macOS use `sh install.sh`/`uninstall.sh`.
- Venv Python: `~/.system1-gateway/venv/Scripts/python.exe` (Windows) or `~/.system1-gateway/venv/bin/python`. `SYSTEM1_INSTALL_DIR` overrides the root.

First work out what the user wants: **install** (default), **upgrade**, **reconfigure**, or **uninstall**.

## Install / upgrade
1. **Python 3.11+.** Windows: `py -3.12 --version` (or `-3.13`/`-3.11`, then `python --version`). Unix: `python3 --version`. If there's none, tell the user how to install it and stop. Don't install system packages yourself.
2. **Upgrade only:** get the newer code first, then continue with step 3.
   - Plugin install: have the user run `/plugin marketplace update system1-gateway`, then `/plugin update system1@system1-gateway` (or update it from the `/plugin` menu). Then re-invoke this skill so it runs from the new copy.
   - Git clone: show `git status` and `git log -1`, and ask before `git pull`.
3. **Install:** `powershell -ExecutionPolicy Bypass -File ./install.ps1` or `sh install.sh`. It's idempotent. Note whether the config file was *created* or *kept*.
4. **Tests:** run `<venv python> -m unittest discover -s tests` from the gateway root. Everything must pass before you continue. From here on, use the venv Python for every script: a bare `python` may be too old, or the Microsoft Store stub on Windows.
5. **Provider.** Read the user config (the path is in the install output). Ask which provider to use:
   - **Laya:** ask for the endpoint (default `http://127.0.0.1:8765`). A non-loopback host needs `allow_remote = true`, which requires the user's explicit OK. The adapter in `system1_gateway/providers/laya.py` was verified against laya 0.3.20. If their Laya is much newer and smoke reports `malformed_response`, suggest `/system1:add-provider`.
   - **No engine yet / unsure which one:** run `/system1:choose-model`. It researches, recommends and installs one, then comes back here at step 6.
   - **Mock:** a deterministic stand-in, for trying the gateway before a real engine exists.
   - **Keep current.**
   Optionally set `fallback` (e.g. `["mock"]`), `timeout_s` and `min_confidence`. Show the diff, then edit.
   If a working engine is already installed (smoke passes in step 6), also offer the **model-routing hook**: `[routing] enabled = true` makes the plugin suggest haiku/sonnet/opus for subagents on each prompt. Offer the calibration log too: `log_dirs` lists the repos whose prompts may be logged. It's off by default. Suggest leaving out repos with confidential work, since the log keeps prompt text on this machine. With no engine yet, skip this: `/system1:choose-model` offers it right after installing one.
6. **Verify:** `<venv python> scripts/smoke.py --question "Rerun the flaky pipeline or block the merge?" --options "rerun the pipeline" "block the merge"`.
   - If Laya is the provider and unreachable because the user has no Laya yet, offer a demo: start `<venv python> tests/fake_laya.py` in the background, re-run smoke, then **stop the fake server**.
   - If smoke fails, switch to `/system1:doctor`.
7. **Register** (ask first; it changes the user-level Claude Code config):
   - `claude mcp get system1`. If it's registered with a different command, ask before `claude mcp remove --scope user system1`.
   - `claude mcp add --scope user --transport stdio system1 -- "<venv python>" -I -m system1_gateway`
     (`-I` stops files in the user's other projects from shadowing the gateway's imports. Keep it.)
     **In PowerShell, write the separator as `'--'` (quoted).** Otherwise PowerShell swallows it when `claude` is the npm `claude.ps1` shim, and the command fails with `unknown option '-I'`.
   - `claude mcp list` should show `system1` as connected. Already-open Claude Code sessions need a restart to pick it up.
8. **Summary:** version installed, config path, provider chain, smoke result, and whether it's registered.

## Reconfigure
Do steps 5, 6 and 8. There's no reinstall; config is read each time the server starts, so restart Claude Code sessions afterwards.

## Uninstall
Confirm first. Then run `uninstall.ps1` / `sh uninstall.sh`, which unregisters the server and deletes the venv. Add `-Purge` / `--purge` **only** if the user explicitly asks to delete their config too. Confirm that `claude mcp list` no longer shows `system1`.

The plugin is uninstalled **last**, because the uninstall scripts ship inside it. Tell the user to run `/plugin uninstall system1@system1-gateway` if they also want the skills gone.
