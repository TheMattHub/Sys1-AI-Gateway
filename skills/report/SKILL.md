---
name: report
description: Report whether System-1 routing is used across sessions and what it saves (reach, hint adherence, subagent cost, net benefit), then offer a focused calibration.
---

# System-1 usage and net-benefit report

Gateway root (holds `scripts/`): two directories above this skill's base directory. Run scripts with the gateway venv Python (`~/.system1-gateway/venv/Scripts/python.exe`, or `.../venv/bin/python`).

The report is read-only and prints aggregates only. It reads Claude Code's own transcripts, which contain every prompt the user wrote. **Never quote prompt or task text from the transcripts**, in the report or anywhere else.

## 1. Run it
`<venv python> scripts/usage_report.py --days 14 --json`. Use `--days` to match what the user asks, e.g. "this week" → 7.

## 2. Present (short, numbers first)

| Area | Fields |
|---|---|
| Reach | `active_since_routing` / `sessions_since_routing`, `hint_rate`, `active_projects` |
| Adherence | spawns after a hint: followed / upgraded / downgraded, `adherence`, `baseline_mix` |
| Money | subagent cost by tier; `realised_savings`; `net_realised` (after hint tokens); `missed_savings` (what upgrades past a hint cost, if the hints were right) |
| Overhead | median hook latency, `hook_seconds_total` |
| Quality | `possible_escalations` (a lower-tier spawn redone at a higher tier in the same turn) and calibration accuracy |
| Shadow | `calibration.shadow`: record-only Agent spawns, System-1's tier vs the orchestrator's (`agree`, `system1_cheaper`), and `accuracy_on_labeled`. With `[routing] hint = false` there are no hinted spawns, so `too_little_data` and adherence are expected: judge by this row instead |
| Calibration | fits, `seed_only`, routing-log `unlabeled` |

State plainly how to read these numbers:
- **Costs** use API list prices from `scripts/prices.json` (dated). A Claude Code subscription bills differently, so treat the dollars as a way to compare tiers, not as the bill.
- **Savings are estimates:** they reprice the same tokens at another tier, and they assume the hinted tier would have done the job. The labels from `/system1:calibrate` are what show whether it would have.
- **"Not active" doesn't mean "not loaded":** the hook is silent when System-1 abstains or the prompt is short. Sessions started before the plugin was updated have no hook at all. For sessions in repos listed in `log_dirs`, `routing_log_entries` counts abstentions too.
- **With `too_little_data`, draw no conclusions.** Say so, and say roughly how many more hinted spawns are needed: at least 10.

## 3. Turn the findings into calibration instructions
Map each flag to a concrete focus. Only include what applies:

| Flag | Instruction for `/system1:calibrate` |
|---|---|
| `labels_pending`, `seed_only_calibration` | "Label the N unlabeled routing-log entries, merge them with `calibration/routing-seed.jsonl`, refit the routing question, write the fit to the user file, and propose shipping it if the data isn't private." |
| `overrides_mostly_upgrade`, `low_adherence` | "Label first the log entries whose `ts` matches these override times: <list `prompt_time` + hint→spawned>. For each, decide whether the hint was too low (label = the spawned tier), or Claude over-escalated (label = the hinted tier). If the hints were mostly right, suggest stronger hint wording that states the measured accuracy. If they were mostly wrong, refit and raise `[routing] min_confidence` to the threshold that reaches 80%." |
| `possible_rework` | "Treat escalated turns as evidence that the hinted tier was too low. Label them with the higher tier." |
| `mostly_abstaining` | "Check the threshold table: if a lower `[routing] min_confidence` still reaches the target accuracy, propose it. Report the change in coverage." |
| `too_little_data` (alone) | No calibration yet. Suggest re-running the report after about 10 more hinted spawns. |

These flags are **not** calibration problems. Suggest `/system1:doctor` instead:
- `routing_disabled`
- `slow_hook`
- `low_reach`, when the routing log also shows few entries (meaning the hook isn't running, rather than abstaining)

The routing log's `ts` is local time without seconds precision beyond the hook call. Tell calibrate to match override times within about ±60 s.

## 4. Offer the calibration
Show the drafted instructions as a short numbered list. Then ask with AskUserQuestion: **"Run /system1:calibrate with these instructions now?"**
- *Yes, run it*
- *Not now*

The automatic "Other" option lets the user edit the instructions.

On yes, invoke the Skill tool with `system1:calibrate` and pass the final instructions as `args`. On no, finish with the report and the instructions, so the user can run `/system1:calibrate` later with them.
