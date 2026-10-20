# How routing and calibration work

Routing and calibration share one idea: ask the engine what it can see in the text, and trust its answer
only as far as measurement shows. This page explains the mechanisms; the steps to use them are in
[Turn on model routing](../how-to/routing.md) and [Calibrate and evaluate](../how-to/calibrate.md).

## Routing asks about features, not about the model

On every prompt, the `UserPromptSubmit` hook ([route_hook.py](../../system1_gateway/route_hook.py)) asks
the engine four yes/no questions about the text, defined in
[routing_features.py](../../system1_gateway/routing_features.py):

- `read_only`: does the task only look something up, check, count or answer, without changing files?
- `design`: does it ask to design, plan, decide between options, research or define an architecture?
- `review`: does it ask to review or audit existing work?
- `specified`: does it name the exact steps, files or plan item? (recorded, not yet used by the rule)

A small rule that you own, [routing_rule.py](../../system1_gateway/routing_rule.py), turns the answers into
a tier: `design` or `review` gives opus, otherwise `read_only` gives haiku, otherwise sonnet. When hints are
on and every answer clears the threshold, Claude gets the tier as a hint for the subagents it spawns.

The features exist because asking directly failed. On 284 labelled tasks, "which model?" scored 46 to 54%
with Laya, 57% with Von and 62% with Gemma 4 E4B, against 52% for always answering "sonnet". Judging how
hard a task is takes reasoning; reading a property off the text does not, and the policy stays yours.

## Outcomes are the labels that count

The orchestrator's model choice is not a correct label; whether that model got the job done is.
[scripts/outcomes.py](../../scripts/outcomes.py) marks a spawn `failed` when its tool result was an error,
its task notification said `failed` or `stopped`, its report says it was blocked, or a later spawn redid the
same task; otherwise `succeeded`. The tier is the model that actually ran. On 30 days of transcripts
(2026-09-30), 279 spawns gave 25 failures, 4 of them doubtful.

`scripts/evaluate.py` scores the rule's safety on those outcomes, the share of failures where the rule would
have picked a higher tier, both with the engine's answers and with the teacher's feature labels. That tells a
weak rule from a weak engine.

## Calibration rescales, it does not re-rank

Engines report probabilities that do not match how often they are right. The gateway rescales them with one
fitted temperature per (provider, model, question); questions too rare for their own fit fall back to a fit
per option count. A temperature never changes which answer wins; it only makes `confidence`, and so
`min_confidence`, mean what it says.

Fits come from two files. `~/.system1-gateway/calibration.json` is fitted on this machine and takes
precedence; [system1_gateway/calibration.json](../../system1_gateway/calibration.json) ships with the
repository, so every install starts calibrated. A fit for another model or checkpoint is ignored, and every
response says `"calibrated": true` or `false`.

The fits shipped now are for Laya `typed-decisions`, from the teacher-labelled seed sets in
[calibration/](../../calibration/):

| Question | n | Accuracy | ECE before → after | Temperature | Accuracy at the threshold |
|---|---|---|---|---|---|
| Routing: which Claude model | 45 | 69% | 0.234 → 0.104 | 0.31 (under-confident) | 77% at 0.6 covering 69% of prompts; 82% at 0.75 covering 24% |
| Is this tool call destructive? | 24 | 88% | 0.217 → 0.136 | 0.27 | 94% at 0.75, covering 75% |

These numbers are measured on the data they were fitted on, from small samples, so treat them as rough.
