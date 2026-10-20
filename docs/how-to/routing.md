# Turn on model routing

Model routing lets System-1 suggest a Claude model (haiku, sonnet or opus) for the subagents Claude spawns.
On every prompt the plugin's hook asks the engine four yes/no questions about the text, a small rule turns
the answers into a tier, and Claude gets a one-line hint. It works in Claude Code only, needs a working
engine, and is off by default.

## 1. Turn it on, record-only

Start by collecting data without hints, so you can check the engine before it influences anything:

```toml
[routing]
enabled = true
hint = false                       # log only; no hint yet
log_dirs = ["~/src/my-project"]    # repos whose prompts may be logged (default: none)
```

`hint` defaults to `true`; set it to `false` until the engine is shown to be ready (step 3). The log is opt-in
per repo: a prompt is logged only when Claude Code's working directory is in one of `log_dirs` or below it.
It keeps prompt text on this machine, in `~/.system1-gateway/logs/routing.jsonl`, so leave out repos with
confidential work.

## 2. Collect and label

Work as usual. The hook also records each Agent spawn next to the model the orchestrator chose, without
changing it. When 30 logged prompts are waiting, the session-start hook suggests `/system1:calibrate`, which
labels them with you and fits the calibration ([Calibrate and evaluate](calibrate.md)).

## 3. Check the engine is ready

```sh
<venv python> scripts/evaluate.py --provider laya     # or von, ollama; one engine at a time on a small GPU
```

The verdict is `READY` only if every feature is at least 85% accurate at the threshold, the rule's safety is
at least 95%, and at least 30 failed spawns are labelled. Then set `hint = true` (or delete the line), and
optionally `[routing] min_confidence` to the threshold calibration recommends.

## 4. See whether it pays off

`/system1:report` reads your Claude Code transcripts and reports, as totals only, how often hints appear,
whether Claude follows them, what subagents cost by tier, and the estimated savings minus the hint overhead.

## What to expect

- **Advisory only:** the hook never blocks or rewrites a prompt.
- **Silent** when the engine abstains, fails or is not installed, for slash commands, for prompts under 10
  words (usually follow-ups whose size depends on the conversation), and for subagent hand-backs.
- **Cost:** about 0.5 s per prompt with Laya warm on a GPU, mostly Python startup; capped at 1.5 s when the
  engine is down.
- **Debugging:** the hook hides its own errors. Run `<venv python> -I -m system1_gateway.route_hook` and paste
  `{"prompt": "..."}` to see what it does.

## The skill picker

The same hook can also name the skill that fits a prompt. It is off and record-only by default:

```toml
[skills]
enabled = true
hint = false
min_confidence = 0.8
```

With Laya it stays dormant and costs nothing: a typical setup has about 100 loadable skills, more than
Laya's 20 options. It wakes on its own for a provider whose `max_options` holds the whole list. Routing and
the picker share the hook's 1.5 s budget, and the picker is skipped when routing uses it up.

Why the hook asks about text features instead of "which model?" is in
[How routing and calibration work](../background/routing-and-calibration.md).
