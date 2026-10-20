# Install the gateway

The gateway installs either as a Claude Code plugin with guided setup or with one script from a clone. Both
put the same stdlib-only package into a user-level venv, `~/.system1-gateway/venv`, and register it once at
user scope, so nothing is added to your projects (no `.mcp.json`). Pick the plugin unless you want the
gateway in another MCP client only.

## With the Claude Code plugin

```
/plugin marketplace add TheMattHub/Sys1-AI-Gateway        # GitHub, or a local clone path
/plugin install system1@system1-gateway
/system1:setup
```

`/system1:setup` installs, runs the tests, sets the provider and registers the server; then restart Claude
Code. The [tutorial](../tutorial/first-decision.md) walks through it.

- **Upgrade:** `/plugin marketplace update system1-gateway`, then `/plugin update system1@system1-gateway`,
  then `/system1:setup` to reinstall.
- **Remove:** `/system1:setup` (uninstall) first, then `/plugin uninstall system1@system1-gateway`. The
  plugin goes last because the uninstall scripts ship inside it.
- **Plugin development:** `claude --plugin-dir <clone>` loads the plugin straight from a clone.

## With the install script

```powershell
# Windows (PowerShell 5.1+ or 7+)
git clone https://github.com/TheMattHub/Sys1-AI-Gateway ; cd Sys1-AI-Gateway
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

```sh
# Linux / macOS
git clone https://github.com/TheMattHub/Sys1-AI-Gateway && cd Sys1-AI-Gateway
sh install.sh
```

The script finds Python 3.11+, creates `~/.system1-gateway/venv`, copies the package into it, creates the
user config from [config.example.toml](../../config.example.toml) if there is none, and prints the
registration command. The installed copy does not depend on the clone. Re-run it to upgrade; set
`SYSTEM1_INSTALL_DIR` to install somewhere else.

## Register with Claude Code

Run the command the installer printed:

```sh
claude mcp add --scope user --transport stdio system1 -- "<venv python>" -I -m system1_gateway
```

- `<venv python>` is `%USERPROFILE%\.system1-gateway\venv\Scripts\python.exe` on Windows and
  `~/.system1-gateway/venv/bin/python` on Linux and macOS.
- `-I` runs Python in isolated mode, so a project file such as `json.py` cannot shadow the gateway's imports.
- **In PowerShell, quote the separator as `'--'`.** When `claude` is the npm `claude.ps1` shim, PowerShell
  swallows a bare `--` and Claude fails with `unknown option '-I'`. The command `install.ps1` prints is
  already quoted.

Check it with `claude mcp list`, or `/mcp` inside Claude Code; remove it with
`claude mcp remove --scope user system1`.

## Use with other MCP clients

The gateway is a standard stdio MCP server, and every client launches the same command: the venv Python with
`-I -m system1_gateway`. On Windows, JSON configs accept forward slashes
(`C:/Users/<you>/.system1-gateway/venv/Scripts/python.exe`).

```json
{ "mcpServers": { "system1": { "command": "<venv python>", "args": ["-I", "-m", "system1_gateway"] } } }
```

| Client | Where it goes |
|---|---|
| Claude Desktop | `claude_desktop_config.json` (Settings, Developer, Edit Config), shape above |
| Cursor | `~/.cursor/mcp.json`, shape above |
| Gemini CLI | `~/.gemini/settings.json`, shape above |
| Windsurf | `~/.codeium/windsurf/mcp_config.json`, shape above |
| VS Code (Copilot) | user `mcp.json` (command *MCP: Open User Configuration*): `{"servers": {"system1": {"type": "stdio", "command": "<venv python>", "args": ["-I", "-m", "system1_gateway"]}}}` |
| Codex CLI | `~/.codex/config.toml`: `[mcp_servers.system1]` with `command = "<venv python>"` and `args = ["-I", "-m", "system1_gateway"]` |

These locations change between client versions, so check your client's MCP docs if one does not work. The
skills and hooks are Claude Code only; the tools behave the same in every client.

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1          # add -Purge to delete the config too
```

```sh
sh uninstall.sh                                                   # add --purge to delete the config too
```

Uninstalling unregisters the MCP server (if `claude` is on PATH), deletes `~/.system1-gateway/venv` and
removes the Windows start-at-login entry. Your config, the engines (Laya is about 6 GB) and the logs stay
unless you pass `-Purge` or `--purge`. Stop the engine before purging, because Windows cannot delete a
running `laya-serve.exe`.
