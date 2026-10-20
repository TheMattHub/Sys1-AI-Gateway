# Release notes

Releases are tagged `system1--v<version>`, the Claude Code plugin convention (`claude plugin tag . --push`),
and listed on [GitHub](https://github.com/TheMattHub/Sys1-AI-Gateway/releases). Each one also gets a
one-word codename from Kahneman's *Thinking, Fast and Slow*, in alphabetical order: minor and patch releases
take the next letter, and major releases break the alphabet and take the authors' names.

## Unreleased

- **Providers:** `systemone` for any server speaking the `/v1/systemone` contract (llama.cpp's `llama-server` with
  Liquid AI's d1, or `engines/systemone/serve.py` for the gte reranker, Qwen3-Reranker, AnyJev and
  OpenThai-SystemOne) and `anthropic` for a hosted Claude model over HTTPS (key from `ANTHROPIC_API_KEY`).
- **Naga study, round 3:** Liquid AI d1-omni-600M and d1-3B, OpenThai-SystemOne and AnyJev on the 100-request TEST2
  set and the model-building sets; d1-3B matches Gemma 4 E4B (licence: commercial use below USD 10 M revenue).
- **New study:** which model tier a Claude Code subagent task needs, with a rerun on the public seed sets.

## 0.2.0 Econs (2026-10-20)

The first public release of the System-1 Gateway: a local MCP server that gives Claude Code and other MCP
clients fast multiple-choice decisions from a pluggable engine, and the studies that show which engine to
pick.

- **Gateway:** three stable tools (`system1_decide`, `system1_capabilities`, `system1_health`) in front of
  Laya, Von, any Ollama chat model or an adapter you add. Python 3.11+ and the standard library only;
  installs as a Claude Code plugin with guided setup or with one script.
- **Study: which System-1 model for naga decisions:** eleven engines on tool choice and model building for
  the naga simulation engine, measured on frozen blind test sets on one 4 GB laptop GPU. The short answer:
  Claude Haiku 5.5 is the most accurate (22 of 25 tool choices over all 90 tools, 37/40 blocks, 30/30
  distributions, about 0.9 s, hosted); Gemma 4 E4B is the most accurate local engine;
  gte-reranker-modernbert-base is the fast one (about 0.1 s). The report covers retries, fewer-choice
  designs that did not pay, and fine-tuning that did not hold on the blind set.
- **Bench:** every number comes from scripts in `bench/naga` that rerun against a clone of the public naga
  repository; new engines plug in with one `eng_*.py` file.
- **Open source:** Apache-2.0, with contribution and security guides and CI on Ubuntu and Windows.
- **Known limit:** the study's sets are small (25 tool questions, 40 blocks, 30 distributions), so a
  difference of one or two rows is noise.

## Codenames

| Release | Codename | Concept |
|---|---|---|
| 0.1.9 | **Anchoring** | An initial number drags every later estimate toward it. The routing hint anchors Claude's model choice |
| 0.1.10 | **Baserate** | Base-rate neglect: a vivid story beats the statistics. Routing now gathers its own base rate, silently, before trusting the hint |
| 0.1.11 | **Coherence** | System 1 builds the most coherent story, not the most likely one. Routing stays out of follow-ups it can't see the story for, and the skill picker waits for an engine that can hold the whole list |
| 0.1.12 | **Denominator** | Denominator neglect: "1 in 10" feels riskier than "10%". Routing is now judged on outcome counts, not on how sure the engine sounds |
| 0.2.0 | **Econs** | The perfectly rational agents of economics, as opposed to Humans. The first public release: engines are chosen by measurement on frozen blind tests (the naga decisions study), not by how sure they sound |
| next | **Framing** | The same facts described differently lead to different choices |
| | **Halo** | Liking one trait colors judgment of all the others |
| | **Illusion** | The illusion of validity: confidence without accuracy, which is exactly what calibration corrects |
| 1.0 | **Kahneman** | |
| 2.0 | **Tversky** | Amos Tversky, Kahneman's research partner behind heuristics and prospect theory |
