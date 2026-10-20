# Configure

The gateway reads one TOML file, and every key in it is optional. It lives at
`%APPDATA%\system1\config.toml` on Windows and `~/.config/system1/config.toml` on Linux and macOS, or at any
path in `SYSTEM1_CONFIG`; the installer creates it from [config.example.toml](../../config.example.toml).
Environment variables override the file, and the file is read each time the server starts, so restart
Claude Code sessions after a change.

## Choose the provider and a fallback

```toml
[gateway]
provider = "laya"         # the primary engine
fallback = ["mock"]       # tried in order on a timeout, an error or a malformed answer; [] by default
timeout_s = 5.0           # per attempt
```

A fallback runs only when the primary fails. It never runs because the primary abstained: an abstention is a
valid answer.

## Set the confidence threshold

```toml
[gateway]
min_confidence = 0.6      # abstain below this
```

A request can override it with its own `min_confidence`. The number only means what it says once a
calibration matches your engine and checkpoint; see [Calibrate and evaluate](calibrate.md).

## Provider settings and secrets

Provider settings go in `[providers.<name>]`, or in environment variables named `SYSTEM1_<NAME>_<KEY>`
(for example `SYSTEM1_LAYA_ENDPOINT`). Secrets such as API keys go only in environment variables, never in
the file. A non-loopback endpoint is refused unless you set `allow_remote = true` for that provider.

## Logs

Logs always go to stderr, because stdout carries the protocol. Set `log_file` to also write a file, and
`log_level = "DEBUG"` to include the question text. Every line carries the request id.

## Pause System-1

`/system1:toggle off` pauses the routing hook, the skill picker and `system1_decide` from the next prompt,
with no restart; `/system1:toggle on` resumes them and `/system1:toggle status` shows the state.

A broken config never stops the server: `system1_health` reports `down` and `system1_decide` returns
`config_error` with the reason. Every key, default and variable is in [Config keys](../reference/config.md).
