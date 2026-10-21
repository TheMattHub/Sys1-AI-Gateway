# System-1 Gateway for Claude Code

[![Accuracy against median latency for the engines in the naga decisions study](docs/screenshots/hero.png)](https://thematthub.github.io/Sys1-AI-Gateway/studies/naga-decisions.html)

*The [interactive version](https://thematthub.github.io/Sys1-AI-Gateway/studies/naga-decisions.html) on the docs site shows each engine's numbers and each kind's own frontier on hover.*

The System-1 Gateway gives Claude Code fast multiple-choice decisions from a small local engine, through one
MCP server with three stable tools: `system1_decide`, `system1_health` and `system1_capabilities`. You pick
the engine (Laya, Von, Liquid AI d1 through llama.cpp, any Ollama chat model, a Hugging Face reranker through a
small local server, a hosted Claude model, or one you add), and below its confidence threshold it abstains,
so Claude reasons the call through itself. Python 3.11+ and the standard library only; installed once at user
scope, it works in every project and with any MCP client.

**Documentation: https://thematthub.github.io/Sys1-AI-Gateway/**

## Quick start

In Claude Code:

```
/plugin marketplace add TheMattHub/Sys1-AI-Gateway
/plugin install system1@system1-gateway
/system1:setup
```

`/system1:setup` installs the gateway into `~/.system1-gateway/venv`, runs the tests and registers the
`system1` MCP server; `/system1:choose-model` recommends and installs an engine for your hardware. Restart
Claude Code, and Claude can call `system1_decide`. The
[tutorial](https://thematthub.github.io/Sys1-AI-Gateway/tutorial/first-decision.html) walks through it, and
[Install the gateway](https://thematthub.github.io/Sys1-AI-Gateway/how-to/install.html) covers the install
script and other MCP clients.

## Which engine?

The [naga decisions study](docs/studies/naga-decisions.md) compares every engine we tried on picking one of
naga's 90 agent tools, on frozen blind test sets and one laptop GPU. Claude Haiku 5.5 is the most accurate on the
search queries an agent writes (69% right first time, about 1 s), and a 150M gte-reranker trained on Claude Opus
5.5's labels comes within noise of it offline (67%) and beats it on people's own wording. Among published local
models Gemma 4 E4B and Qwen3-Reranker-0.6B come next at 3 to 6 s, Laya is the fast pick when a wrong tool can be
retried, and Liquid AI's d1-3B is the System-1 model level with the hosted ones on people's requests (13.7 s on
4 GB; commercial use below USD 10 M revenue).
The study page has the numbers, the retries chart and the caveats.

## Documentation

- [Tutorial: your first decision](https://thematthub.github.io/Sys1-AI-Gateway/tutorial/first-decision.html)
- [How-to guides](https://thematthub.github.io/Sys1-AI-Gateway/how-to/install.html): install, engines,
  configure, model routing, calibrate, add a provider, troubleshoot
- [Reference](https://thematthub.github.io/Sys1-AI-Gateway/reference/tools.html): tools and schema, config
  keys, slash commands and scripts, providers
- [Background](https://thematthub.github.io/Sys1-AI-Gateway/background/system-1.html): what System-1 means
  here, how routing and calibration work
- [Studies](https://thematthub.github.io/Sys1-AI-Gateway/studies/naga-decisions.html) and
  [release notes](https://thematthub.github.io/Sys1-AI-Gateway/release-notes.html)
- For AI agents: [llms.txt](https://thematthub.github.io/Sys1-AI-Gateway/llms.txt)

## Licence

Apache-2.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE). Contributions are welcome: see
[CONTRIBUTING.md](CONTRIBUTING.md); to report a vulnerability, see [SECURITY.md](SECURITY.md).
