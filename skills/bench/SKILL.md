---
name: bench
disable-model-invocation: true
description: Run, extend or rerun the naga System-1 bench (bench/naga) - add an engine, a test set or a trained student, and rebuild the tables and charts of the naga decisions study.
---

# The naga System-1 bench

The bench measures models on the choices an assistant makes while it drives naga, above all which of the 90 agent tools to call. The study it backs is `docs/studies/naga-decisions.md`, and the full record is `bench/naga/RESULTS.md`. **REQUIRED BACKGROUND:** the method (several writers, an agent-phrased set, rank all options, the teacher gate, retries, sign test) is in the `benchmarking-small-model-pickers` skill. Read it first if it is installed. Otherwise read the study's "How we test" section.

## Where things are

| Path | What |
|---|---|
| `bench/naga/distill/test3.jsonl` | TEST3: 150 requests by four writers (frozen) |
| `bench/naga/distill/agent3.jsonl` | AGENT3: 274 find_tool queries written by the agent (frozen) |
| `bench/naga/distill/test2.jsonl`, `data/` | the earlier sets (frozen; supporting evidence only) |
| `bench/naga/distill/train2.jsonl`, `labels/` | training requests and teacher labels |
| `bench/naga/distill/results3/`, `results4/` | one JSONL per engine and task: ranking, gold, latency per row |
| `bench/naga/eng_*.py` | one script per kind of engine; `common.run(name, decide)` writes the result file |
| `bench/naga/plot.py` | hero chart, retries chart, `docs/assets/engines.json`, and the table on stdout |

Never edit a frozen set. Put doubts in `distill/NOTES.md`.

## Run an engine on the trusted sets

The bench venv is `~/.system1-gateway/engines/bench/Scripts/python.exe`. The hosted Claude engines run on a Python with `anthropic`, and their key is read in-process, never on a command line. Run from `bench/naga`:

```powershell
$env:BENCH_ROUND = 'test3'    # TEST3 (+ TEST2, HELD_OUT_2) -> distill/results3
$env:BENCH_ROUND = 'agent3'   # AGENT3 -> distill/results4
$env:BENCH_TASKS = 'Tall'     # tool choice over all 90 tools
python eng_hf.py <engine>     # or eng_anthropic.py haiku|opus, eng_d1.py, ...
python eng_hf.py tuned <model folder> <result name>   # any local cross-encoder, e.g. a new student
```

A result file is appended row by row, so a rerun goes on where it stopped. `BENCH_SPLITS=TEST3` limits a run to some splits.

## Add something

- **A new engine:** add a `decide(item) -> ranking` in an `eng_*.py`, run it on both sets, add it to `ENGINES` in `plot.py` with its kind, and add it to `CHART` only if the story needs it.
- **A new student:** run `distill/label.py <teacher>` (cached, resumable), then `distill/train.py <teacher>`. Training stops at a time budget and exits with code 3, so rerun it until it exits with 0. Then run `eng_hf.py tuned` on both sets. Pay for a teacher's labels only after it beats the current best teacher as a picker on TEST3.
- **A new test set:** follow `distill/write3.py` (writers) or `distill/agent3.py` (agent phrasing), and commit the set before any engine sees it.

## Rebuild the page

Run `python plot.py` (bench venv). It redraws `docs/screenshots/hero.png`, `retries.png` and `docs/assets/engines.json`, and prints the full engine table for the study page. Update the page's numbers from that output, never by hand. Then:
- run `python -m unittest discover -s tests`;
- run `python -m mkdocs build --strict`;
- check the interactive chart and its table fallback.

Trained models are never committed. `distill/models/` is git-ignored.
