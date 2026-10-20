---
name: calibrate
description: Label logged System-1 decisions, fit confidence calibration, measure accuracy and set thresholds. Use when asked to calibrate or tune the System-1 model, or when prompted that routing prompts await labeling.
---

# Calibrate the System-1 model

Why: System-1 engines report probabilities that don't match how often they're right. Laya's model card says it ships over-confident. On our routing task it measured *under*-confident (fitted T ≈ 0.31). Either way, `min_confidence` means nothing until a temperature is fitted on the user's own decisions. Temperature never changes which answer wins, so **accuracy** is the number that decides whether to trust the model at all.

Gateway root (holds `scripts/`, `calibration/`, `system1_gateway/`): two directories above this skill's base directory. Use the gateway venv Python (`~/.system1-gateway/venv/Scripts/python.exe`, or `.../venv/bin/python`) for every script.

Never commit. Ask before editing the user config or writing a calibration file.

**If this skill was invoked with instructions** (typically from `/system1:report`), treat them as the focus: follow their labeling priorities, fits and threshold goals within the steps below, and say at the end which of them were met. The rules here still apply (ask before writing, keep prompt text local).

## 1. Check the basics
- Run `<venv python> scripts/smoke.py`: health must be `ok`, with the intended provider and model. Calibration is per (provider, model); entries for another checkpoint are ignored automatically.
- Read the provider's limitations. For Laya, see the docstring of `system1_gateway/providers/laya.py` and the "honest limitations" section of the model card. If the provider has changed, re-check them online first (`/system1:choose-model` has the sources).

## 2. Gather labeled data
Sources, in order of value:
1. **The routing log** `~/.system1-gateway/logs/routing.jsonl`: real prompts from the repos listed in `[routing] log_dirs`. Entries have `"label": null` until labeled.
2. **Seed sets** in `calibration/`: `routing-seed.jsonl` and `yes-no-seed.jsonl`, labeled by a teacher model. Use them to bootstrap, or when the log is small.
3. **User-provided decisions** for other questions, as JSONL: `{"question", "options", "context", "label"}`.

**Labeling the log (teacher + user):**
- Propose a label for each unlabeled entry as the teacher. Use the user's routing rules from memory if present: haiku for mechanical work, sonnet for well-specified implementation and tests, opus for design, architecture, refactors and subtle bugs; map anything "fable"/coordination to opus.
- Entries with `"source": "agent"` are Agent spawns recorded by the PreToolUse hook: the prompt is the orchestrator's brief to the subagent, `chosen` is the model it picked. Propose `chosen` as the label (`inherit` and `fable` → opus) unless the brief clearly fits another tier, and flag those. Hand-back messages are no longer logged; old ones carry `"label": "skip"`, which `calibrate.py` ignores.
- Show a compact table: `#`, repo (`cwd` basename), prompt (first ~80 chars), proposed label, and a note on the doubtful ones. Ask the user to correct only the ones they disagree with. Batches of about 25 are easiest to review.
- Write the labels back into the log, adding `"label_source": "teacher"` or `"user"` to each entry. Change nothing else, and never add or remove entries. Other sessions may append while you work: write to `routing.jsonl.tmp`, append any lines that arrived after your read (unlabeled), then `os.replace` it over the log. Once an entry has a label, the session hook stops counting it as pending.
- The log holds prompt text from the user's repos. Keep it local: don't copy it into the repo or any shared place.

## 2b. Feature labels and outcomes

Routing asks four yes/no questions about the text (`read_only`, `design`, `review`, `specified`; the exact wording is in `system1_gateway/routing_features.py`), and `system1_gateway/routing_rule.py` maps the answers to a tier. So there are two kinds of label.

- **Feature labels** (what the text says, near-objective):
  - For entries without `feature_labels`, propose yes/no for all four, as the teacher.
  - Show a compact table (`#`, first ~80 chars, the four proposed answers) and have the user correct only the disagreements.
  - Write them back as `"feature_labels": {"read_only": "yes", ...}` plus `label_source`, with the same safe write as above.
- **Outcomes** (did the model that ran the spawn get it done?):
  - Run `<venv python> scripts/outcomes.py --apply`. It proposes an outcome for every Agent spawn from the transcripts and writes it to the log (`outcome_source: "auto"`).
  - Show its doubtful list and ask the user about those only.
  - Record each answer as `outcome` with `outcome_source: "user"` and `outcome_doubtful: false`.
- **Evaluate an engine:** run `<venv python> scripts/evaluate.py [--provider laya|von|ollama]`, one engine at a time on a small GPU. Report the verdict (`READY` / `NOT READY`) and the unmet bars. The rule's safety is measured twice: with the engine's answers, and with the teacher feature labels. If the teacher version is unsafe too, the rule needs changing, not the engine.

## 3. Fit and measure
`calibrate.py` fits a temperature per question, and that now includes the four feature questions, learned from `feature_labels`.

Run `<venv python> scripts/calibrate.py <data.jsonl> [--target-accuracy 0.8]`, first without `--write`/`--ship`, and read the report:
- **accuracy** is what the model gets right. Below about 60% on routing, calibration alone won't make it useful (see step 5).
- **ECE** (calibration error): before → after. After should be clearly lower.
- **AUROC** measures whether confidence separates right from wrong answers. At 0.5 thresholds are useless; aim for 0.7+.
- **The threshold table**: coverage vs. accuracy per `min_confidence`. `recommended_threshold` is the lowest threshold reaching the target accuracy on enough examples.

Caveats to tell the user: the fit and the table are measured on the same data (one parameter, so the overfit is small, but the threshold is optimistic). With fewer than about 50 examples, treat the numbers as rough. Merge old and new labeled files when refitting, rather than fitting on the newest batch alone.

## 4. Apply (ask first)
- **This machine only:** `--write` saves to `~/.system1-gateway/calibration.json`, which takes precedence over the shipped file.
- **Every install:** `--ship` saves to `system1_gateway/calibration.json` in the repo. Only do this when the data isn't private: the fit itself contains no prompt text, but mention that the seed/labeled file names are recorded in it. The user commits it; then re-run the installer here.
- **Threshold:** set `[routing] min_confidence = <recommended>` in the user config for routing hints, or `[gateway] min_confidence` for all decisions. Show the diff first.
- Re-run the installer (`install.ps1` / `install.sh`) so the gateway venv gets the new shipped file. Then re-run smoke with a routing-style question and show that `calibrated` is `true`.

## 5. When accuracy is the problem
Temperature can't fix these. Suggest them in this order:
1. **Question and option wording.** For routing, try clearer tier descriptions in `TIERS` in `system1_gateway/route_hook.py`, in a git clone. Refit and compare accuracy on the same labeled file, and keep a change only if accuracy improves. Changing `TIERS` or `QUESTION` means refitting, since the fit is keyed by question and option count.
2. **Known structural limits.** For Laya:
   - no `noul`: already asked as a yes/no choice
   - at most 20 options: use a coarse-to-fine hierarchy
   - English-only checkpoints abstain on non-Latin text: use `model = "multilingual"` if the user works in such scripts
   - `score` is weak: prefer `choice`
3. **Fine-tuning.** Laya's RLCD notebook (`notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb` in `NandhaKishorM/laya`) trains on labeled decisions in about 4 h on free Kaggle GPUs. It's worth it once there are a few hundred labeled examples. The result is a new checkpoint, so the adapter's `model` setting and the calibration both need updating. Describe this; don't start it without the user.

## 6. Report
Summarize:
- data used (sources, n, labels corrected by the user)
- accuracy, ECE before → after, AUROC
- the chosen threshold with its coverage and accuracy
- where the fit was written, and what's left to do

Next run: the session hook will say when 30 more prompts are waiting.
