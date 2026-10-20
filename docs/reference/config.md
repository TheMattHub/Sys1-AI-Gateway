# Config keys

The config file is `%APPDATA%\system1\config.toml` on Windows and `~/.config/system1/config.toml` (or
`$XDG_CONFIG_HOME/system1/config.toml`) on Linux and macOS, or the path in `SYSTEM1_CONFIG`. Every key is
optional, environment variables override the file, and an unknown key in `[gateway]`, `[routing]` or
`[skills]` is a config error. The commented template is [config.example.toml](../../config.example.toml).

## [gateway]

| Key | Default | Env var | Meaning |
|---|---|---|---|
| `provider` | `"laya"` | `SYSTEM1_PROVIDER` | primary provider |
| `fallback` | `[]` | `SYSTEM1_FALLBACK` (comma list) | providers tried in order on a timeout, error or malformed answer |
| `timeout_s` | `5.0` | `SYSTEM1_TIMEOUT_S` | limit per attempt, in (0, 300] |
| `min_confidence` | `0.6` | `SYSTEM1_MIN_CONFIDENCE` | abstain below this, in [0, 1]; a request can override it |
| `log_level` | `"INFO"` | `SYSTEM1_LOG_LEVEL` | `DEBUG` also logs question text |
| `log_file` | `""` | `SYSTEM1_LOG_FILE` | logs always go to stderr; set this to also write a file |

## [routing]

| Key | Default | Env var | Meaning |
|---|---|---|---|
| `enabled` | `false` | `SYSTEM1_ROUTING_ENABLED` | the model-routing hook |
| `hint` | `true` | `SYSTEM1_ROUTING_HINT` | `false` logs only and adds no hint |
| `log_dirs` | `[]` | `SYSTEM1_ROUTING_LOG_DIRS` (`;` on Windows, `:` elsewhere) | repos whose prompts may be logged; none by default |
| `log_file` | `"~/.system1-gateway/logs/routing.jsonl"` | `SYSTEM1_ROUTING_LOG_FILE` | the routing log |
| `min_confidence` | the `[gateway]` value | `SYSTEM1_ROUTING_MIN_CONFIDENCE` | routing's own threshold, from calibration |

## [skills]

| Key | Default | Env var | Meaning |
|---|---|---|---|
| `enabled` | `false` | `SYSTEM1_SKILLS_ENABLED` | the skill picker |
| `hint` | `false` | `SYSTEM1_SKILLS_HINT` | `false` records to the routing log with `"source": "skill"` |
| `min_confidence` | `0.8` | `SYSTEM1_SKILLS_MIN_CONFIDENCE` | the picker's threshold |

## [providers.&lt;name&gt;]

Each provider reads its own table, and every key can also be set as `SYSTEM1_<NAME>_<KEY>` (for example
`SYSTEM1_LAYA_ENDPOINT`). The keys of each provider are in [Providers](providers.md).

## Other environment variables

| Variable | Meaning |
|---|---|
| `SYSTEM1_CONFIG` | path of the config file; a missing file is a config error |
| `SYSTEM1_INSTALL_DIR` | install root instead of `~/.system1-gateway` (venv, engines, logs, pause file) |
