# Contributing

Thanks for looking. Bug reports, new providers and small, focused pull requests are welcome.

## Before you open a pull request

- Run the tests from the repo root with Python 3.11 or newer: `python -m unittest discover -s tests -v`.
  They need no third-party packages and make no network calls beyond 127.0.0.1.
- Every change to the gateway comes with a test. A bug fix comes with a test that fails without it.
- Keep the gateway stdlib-only: a new dependency needs a clear reason.
- To add an engine, follow "Add a provider" in the README. The MCP tools and schemas stay the same.
- English, ASCII in code and logs, `logging` rather than `print` (stdout is the MCP protocol).

## Bench changes

The scripts in `bench/naga` need GPUs and models, so CI does not run them. If you change a script,
say which engines you reran. Never tune against the frozen sets in `bench/naga/data`.

## Reporting a bug

The gateway version, your provider and its model, the config (without secrets), what you
expected and what you got. `system1_health` output helps.
