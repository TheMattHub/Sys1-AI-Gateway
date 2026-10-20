# Calibrate and evaluate

Calibration makes an engine's confidence mean what it says, so that `min_confidence` is a real threshold.
The repository ships fits for Laya `typed-decisions`, so a fresh install starts calibrated for that
checkpoint; any other engine, or your own prompts, needs a fit of its own. The guided way is
`/system1:calibrate`; this page shows the scripts it runs.

All scripts run with the gateway venv Python (`<venv python>` below), from a clone or from the plugin copy.

## 1. Label decisions

`/system1:calibrate` labels the routing log with you: Claude proposes a label for each entry and you correct
only the ones you disagree with. It also proposes yes/no labels for the four routing features. Seed sets
labelled by a teacher model are in [calibration/](../../calibration/), and you can add your own decisions
as JSONL lines: `{"question", "options", "context", "label"}`.

For Agent spawns, the outcome is the better label: did the model that ran it get the job done?

```sh
<venv python> scripts/outcomes.py --apply
```

It proposes `failed` or `succeeded` for every spawn from your transcripts, writes it into the log, and lists
the doubtful ones for you to confirm.

## 2. Fit and measure

```sh
<venv python> scripts/calibrate.py DATA.jsonl --target-accuracy 0.8
```

It re-asks every example live, fits one temperature per question, and reports accuracy, calibration error
(ECE) before and after, AUROC, and a threshold table of coverage against accuracy. Read it before you save:

- `--write` saves the fit for this machine (`~/.system1-gateway/calibration.json`, which takes precedence).
- `--ship` saves it into the repository's `system1_gateway/calibration.json`, for every install.

Then re-run the installer so the venv gets a shipped fit, and set `[routing] min_confidence` (routing only)
or `[gateway] min_confidence` (all decisions) to the recommended threshold.

## 3. Evaluate an engine for routing

```sh
<venv python> scripts/evaluate.py --provider laya
```

It is read-only and reports per-feature accuracy and AUROC, the rule's safety and savings, and a verdict,
`READY` or `NOT READY`. The bars can be changed with `--min-feature-accuracy`, `--min-safety` and
`--min-failures`.

## When accuracy is the problem

A temperature never changes which answer wins, so it cannot fix a wrong engine. Try clearer question and
option wording first, then the engine's known limits (for Laya: at most 20 options, English-only checkpoints
on non-Latin text), then fine-tuning once you have a few hundred labelled examples. Fits are measured on the
data they were fitted on and from small samples, so treat the numbers as rough.

How the calibration itself works is in
[How routing and calibration work](../background/routing-and-calibration.md).
