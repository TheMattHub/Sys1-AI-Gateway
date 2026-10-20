# System-1 Gateway

The System-1 Gateway gives Claude Code fast multiple-choice decisions from a small local engine, through
one MCP server with three stable tools. You pick the engine (Laya, Von, any Ollama chat model, or one you
add), and Claude sees the same tools whichever one answers. Python 3.11 or later and the standard library
only; version 0.2.0, released 2026-10-20.

In Claude Code, three commands install it:

```
/plugin marketplace add TheMattHub/Sys1-AI-Gateway
/plugin install system1@system1-gateway
/system1:setup
```

After a restart Claude can ask it a judgement call. One `system1_decide` call and its answer, here from the
built-in `mock` provider (latencies set to 0):

```json
{"question": "Rerun the flaky pipeline or block the merge?",
 "options": ["rerun the pipeline", "block the merge"]}
```

```json
{"schema_version": "1", "request_id": "demo-1", "status": "decided",
 "decision": "rerun the pipeline", "confidence": 0.9,
 "rationale": "mock provider: always picks the first option", "provider": "mock",
 "probabilities": {"rerun the pipeline": 0.9, "block the merge": 0.09999999999999998},
 "calibrated": false, "latency_ms": 0,
 "attempts": [{"provider": "mock", "outcome": "ok", "latency_ms": 0, "detail": null}], "error": null}
```

Three things set it apart. It abstains instead of guessing: below the confidence threshold the answer is
`abstained` and Claude reasons it through itself. The threshold means something, because each engine's
probabilities are calibrated on labelled decisions. And the choice of engine rests on measurement: the
[naga decisions study](studies/naga-decisions.md) compares eleven engines on frozen blind test sets.

![Accuracy against median latency for the engines in the naga decisions study](screenshots/hero.png)

<div class="grid cards" markdown>

-   **Claude Code user**

    ---

    Install it, pick an engine, make a first decision, then turn on model routing.

    [Your first decision](tutorial/first-decision.md), [Install an engine](how-to/engines.md) and
    [Turn on model routing](how-to/routing.md)

-   **Choosing a decision model**

    ---

    Speed against accuracy on real decisions, on one laptop GPU, with the caveats.

    [Which model for naga decisions](studies/naga-decisions.md) and [Providers](reference/providers.md)

-   **Contributor**

    ---

    Add an engine adapter: one file and one registry line; the tools stay the same.

    [Add a provider](how-to/add-provider.md) and
    [CONTRIBUTING.md](../CONTRIBUTING.md)

-   **AI agent**

    ---

    Read the site as plain text and validate against the published schema.

    [llms.txt](https://thematthub.github.io/Sys1-AI-Gateway/llms.txt),
    [llms-full.txt](https://thematthub.github.io/Sys1-AI-Gateway/llms-full.txt) and [Tools and schema](reference/tools.md)

</div>

Every page also has a Markdown copy: replace `.html` with `.md` in its address.
