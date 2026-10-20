# Naga System-1 bench

This folder holds the bench behind the [study report](../../docs/studies/naga-decisions.md): it measures System-1 models on the decisions an assistant makes while using the [naga](https://github.com/TheMattHub/naga) simulation engine. The frozen test sets, every raw result and the scripts that made the tables are all here, so a new engine can be added and compared on the same rows. [RESULTS.md](RESULTS.md) has the full tables, and [plot.py](plot.py) draws the charts.

## What is here

- `data/`: the frozen blind test sets for model building (blocks, distributions, record fields) and `CORRECTIONS.md`. Never tune against them.
- `derived/`, `derived2/`: what the engine exported for round 1 and round 2 (tool documents, TRAIN/TEST questions with `find_tool`'s top 10, block and distribution descriptions). Committed, so the engines run without a naga clone.
- `eng_*.py`, `tune.py`, `retry.py`, `phase4.py`: one script per kind of engine, the fine-tune, the retry study and the fewer-choices study.
- `results/`, `results2/`: one JSONL file per engine and task (ranking, confidence, latency per decision), for round 1 and round 2.
- `report.py`, `report2.py`: rebuild the tables in `RESULTS.md`. `plot.py` draws `docs/screenshots/*.png`.

## Rerun

You need Windows PowerShell 5.1 or newer, an NVIDIA GPU (the numbers were taken on an RTX A500 with 4 GB), a Python 3.12 with naga's dependencies, and a clone of naga next to this repo (`..\naga`). Each engine runs in its own venv under `~/.system1-gateway/engines` (the bench venv, Laya, Von; Gemma 4 runs through Ollama).

```powershell
git clone https://github.com/TheMattHub/naga ..\naga
powershell -ExecutionPolicy Bypass -File bench/naga/run.ps1                      # round 1, every engine
powershell -ExecutionPolicy Bypass -File bench/naga/run.ps1 -Round 2 -Only gemma4 # round 2, one engine
```

`-Naga <path>` points at another clone, and `-Only` takes an engine name or `retry-tuned`, `retry-laya`, `phase4-tuned`, `phase4-gte`, `phase4-laya`. Seeds are fixed, and latency is the wall clock per decision on one machine, so expect your times to differ.

## Reproducing the exports

The step that reads naga is `export_data.py`. It needs `nagasim` and `tests/test_toolsearch.py` from a naga clone, and both are in the public repo. Two things differ from the committed data:
- Round 1 (`derived/`) was exported before the descriptions were made fuller, so exporting from today's naga gives round 2's texts, not round 1's. Keep the committed `derived/` to compare with round 1.
- Round 2 (`derived2/`) matches today's naga except one distribution text: `NegativeBinomial` was later corrected to say it counts failures before r successes, not trials. Nothing else changed.

The fine-tuned model (`models/`) is a local training product and is not committed; `tune.py` rebuilds it.
