# Which model tier does a Claude Code subagent task need?

This study asks whether a System-1 engine can pick the Claude model a subagent task needs, and finds that asking it
directly works on easy synthetic prompts and failed on real work. The gateway's routing hook therefore asks the
engine about features of the task and lets a small rule pick the tier. The numbers below come from
[bench/routing/routing.py](../../bench/routing/routing.py), and the history from the earlier private study, of
which only aggregates are published.

## The question

When Claude Code spawns a subagent, it picks a model: a small, fast one (haiku) for mechanical work, a mid one
(sonnet) for well-specified implementation, a large one (opus) for design, review and subtle bugs. A wrong pick
either wastes money and time or hands a hard task to a model that fails it. A System-1 engine answers in tens of
milliseconds, so if it could make that pick from the task text, every spawn could be routed for free.

## What happened before

Asking the engine "which model?" did not work on real tasks. On 284 labelled tasks from the author's own Claude Code
sessions, direct choice scored 46 to 54% with Laya, 57% with Von and 62% with Gemma 4 E4B, against 52% for always
answering "sonnet". Judging how hard a task is takes reasoning, which is what a System-1 model does not do.

The labels that count are outcomes, not the orchestrator's choices. Over 30 days of transcripts (to 2026-09-30),
279 spawns gave 25 failures, 4 of them doubtful ([scripts/outcomes.py](../../scripts/outcomes.py) marks a spawn
failed when its result was an error, it was stopped, it reported being blocked, or a later spawn redid it). With
so few failures, no tier policy can yet be shown safe, and `scripts/evaluate.py` says so.

## Why features and a rule

Reading a property off the text is a System-1 task; judging difficulty is not. So the hook asks four yes/no
questions ([routing_features.py](../../system1_gateway/routing_features.py)): is the task read-only, is it design,
is it a review, does it name the exact steps. A rule you own ([routing_rule.py](../../system1_gateway/routing_rule.py))
maps the answers to a tier: design or review gives opus, otherwise read-only gives haiku, otherwise sonnet. The
policy stays readable and editable, and a wrong tier can be traced to one wrong answer or to the rule.
[How routing and calibration work](../background/routing-and-calibration.md) has the mechanism.

## The rerun on the public seeds

Every engine that can answer a choice or a yes/no question was rerun on the two public seed sets, through its
gateway provider exactly as the hooks ask: [calibration/routing-seed.jsonl](../../calibration/routing-seed.jsonl)
(45 prompts, 15 per tier, teacher labels) and [calibration/yes-no-seed.jsonl](../../calibration/yes-no-seed.jsonl)
(24 tool calls: is this destructive or hard to reverse?). "Direct choice" is the retired "which model?" question
over the three tiers; "features + rule" asks the four features in one pass and applies the rule; "below" counts
the unsafe misses, a tier under the label (or none). Run on 2026-10-21 on the laptop of the naga study (RTX A500,
4 GB).

| engine | provider | direct choice | below | features + rule | below | yes/no (destructive) | median ms: direct / features / yes-no |
|---|---|---|---|---|---|---|---|
| anyjev | systemone | 23/45 | 18 | 16/45 | 14 | 12/24 | 200 / 515 / 136 |
| d1-3b | systemone | 40/45 | 3 | 32/45 | 2 | 23/24 | 153 / 399 / 83 |
| d1-omni | systemone | 29/45 | 9 | 20/45 | 6 | 20/24 | 25 / 65 / 15 |
| gemma4 | ollama | 41/45 | 3 | 18/45 | 0 | 24/24 | 622 / 2486 / 510 |
| gte | systemone | 30/45 | 6 | 16/45 | 14 | 11/24 | 25 / 64 / 21 |
| haiku | anthropic | 43/45 | 2 | 30/45 | 3 | 24/24 | 1111 / 3976 / 995 |
| laya | laya | 31/45 | 5 | 18/45 | 0 | 21/24 | 42 / 57 / 38 |
| openthai-ollama | ollama | 21/45 (1 unanswered) | 20 | 9/45 (19 unanswered) | 20 | 9/24 (3 unanswered) | 79 / 339 / 66 |
| openthai | systemone | 37/45 | 2 | 19/45 | 0 | 23/24 | 99 / 378 / 115 |
| qwen3-rerank | systemone | 24/45 | 0 | 15/45 | 0 | 12/24 | 81 / 246 / 60 |
| von | von | 35/45 | 7 | 24/45 | 4 | 22/24 | 51 / 189 / 29 |

Always answering sonnet: 15/45.

On these seeds direct choice beats the rule for every engine, the opposite of the real-task result. The best are
Claude Haiku 5.5 (43/45, hosted), Gemma 4 E4B (41/45, 0.6 s) and Liquid AI's d1-3B (40/45, 0.15 s), against 15/45
for always answering sonnet. The rule loses mostly by design: it sends every edit that is not read-only to sonnet,
while the seeds label small edits (renames, typo fixes) haiku, so 15 haiku rows are out of its reach unless they
are lookups. On safety the rule does better: Gemma, Laya and OpenThai-SystemOne never route a task below its label
through the rule, against 2 to 5 times by direct choice. The rerankers (gte, Qwen3-Reranker) and AnyJev on a 1.7B
base are near chance on yes/no, because "yes" and "no" carry no text for a reranker to match; they suit choices
whose options describe themselves.

The caveat outweighs the ranking. The seeds are small (45 and 24 rows) and synthetic: a teacher model wrote clean
one-line prompts whose tier is plain from the words, unlike real requests that depend on the conversation, so a
high direct-choice score here does not undo the 284-task result. The rule stays the gateway's default, and an
engine should be judged with `scripts/evaluate.py` on your own outcome-labelled spawns before routing is turned
on. Per-row answers are in [bench/routing/results/](../../bench/routing/results/).
