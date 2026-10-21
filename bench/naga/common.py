"""Shared bench plumbing, stdlib only so every engine venv can import it.

An item is one decision: {id, task, split, text, options, docs, gold}. `options` are label names,
`docs[label]` the label's document (tool doc, block/distribution one-liner), `gold` the accepted labels.
An engine maps an item to {"ranking": [label, ...] best first, "confidence": float} and run() stores one
JSON line per item in results/<engine>.<task>.jsonl, with the measured latency."""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Round 2 (BENCH_ROUND=2): fuller descriptions, T also over all 90 tools ("Tall"), no fields (their texts did not
# change); its data and results live beside round 1's, which stay as they were.
R2 = os.environ.get("BENCH_ROUND") == "2"
DATA, DERIVED, RESULTS = HERE / "data", HERE / ("derived2" if R2 else "derived"), HERE / ("results2" if R2 else "results")
TASKS = ("T", "Tall", "blocks", "distributions") if R2 else ("T", "blocks", "distributions", "fields")
# Distillation (BENCH_ROUND=distill): T and Tall on TEST2 and HELD_OUT_2, data and results under distill/.
if os.environ.get("BENCH_ROUND") == "distill":
    R2, DERIVED, RESULTS, TASKS = True, HERE / "distill" / "derived", HERE / "distill" / "results", ("T", "Tall")
# Round 4 (BENCH_ROUND=test3): TEST3 (multi-writer, distill/test3.jsonl) beside TEST2 and HELD_OUT_2, results under
# distill/results3 (the TEST2 and HELD_OUT_2 rows of engines run before are copied in, so only TEST3 runs).
if os.environ.get("BENCH_ROUND") == "test3":
    R2, DERIVED, RESULTS, TASKS = True, HERE / "distill" / "derived3", HERE / "distill" / "results3", ("T", "Tall")
# BENCH_TASKS picks tasks in any round: one task per call fits a time box (round 3 runs blocks and
# distributions in round 2, T and Tall in distill).
TASKS = tuple(os.environ.get("BENCH_TASKS", ",".join(TASKS)).split(","))

# fields.jsonl corrections, see data/CORRECTIONS.md (1-based row -> (answer, also_ok) or None = dropped).
FIELD_SETS = {"goal": ["id", "text", "kpi", "low", "high", "precision", "share_above"],
              "assumption": ["id", "text", "value", "source", "check"],
              "source": ["id", "text", "input"],
              "validation": ["level", "passed", "text"],
              "scenario": ["name", "goal", "overrides"]}
FIELD_FIX = {3: ("kpi", []), 5: ("text", []), 7: None, 8: None, 9: None, 10: None, 11: None,
             12: ("id", []), 13: ("text", []), 14: ("text", []), 15: ("text", ["id"]), 16: None,
             18: ("text", []), 21: None, 22: None, 23: None, 24: None, 25: None, 26: None, 27: None,
             28: None, 29: ("overrides", []), 30: ("name", [])}


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load(name):
    return json.loads((DERIVED / name).read_text(encoding="utf-8"))


def items(task: str) -> list[dict]:
    if task in ("T", "Tall"):
        tools = _load("tools.json")
        out = []
        for split, rows in _load("tool_queries.json").items():
            for i, r in enumerate(rows):
                opts = r["candidates"] if task == "T" else list(tools)     # "Tall": all 90 tools, catalogue order
                out.append({"id": f"{split}-{i}", "task": task, "split": split, "text": r["query"],
                            "options": opts, "docs": {n: tools[n]["doc"] for n in opts},
                            "summaries": {n: tools[n]["summary"] for n in opts}, "gold": r["gold"]})
        return out
    if task in ("blocks", "distributions"):
        labels = _load(f"{task}.json")
        docs = {k: f"{k}: {v}" for k, v in labels.items()}
        return [{"id": f"TEST-{i}", "task": task, "split": "TEST", "text": r["text"], "options": list(labels),
                 "docs": docs, "summaries": labels, "gold": [r["answer"], *r["also_ok"]]}
                for i, r in enumerate(_jsonl(DATA / f"{task}.jsonl"))]
    if task == "fields":
        out = []
        for row, r in enumerate(_jsonl(DATA / "fields.jsonl"), start=1):
            fix = FIELD_FIX.get(row, (r["answer"], r["also_ok"]))
            if fix is None:
                continue
            opts = FIELD_SETS[r["context"]]
            gold = [fix[0], *fix[1]]
            assert all(g in opts for g in gold), (row, gold)
            out.append({"id": f"TEST-{row}", "task": task, "split": "TEST", "text": r["text"],
                        "context": r["context"], "options": opts,
                        "docs": {f: f"{r['context']} field {f}" for f in opts}, "gold": gold})
        return out
    raise ValueError(task)


def kind(item) -> str:
    """The task family of an item: "Tall" is T with a longer option list."""
    return "T" if item["task"] == "Tall" else item["task"]


def question(item) -> str:
    """The one instruction the engines that take one get (no per-engine prompt variations)."""
    return {"T": "Which tool should the assistant call for this request?",
            "blocks": "Which simulation block type models this sentence?",
            "distributions": "Which probability distribution fits this description?",
            "fields": f"Which field of a study {item.get('context')} record does this key or phrase mean?"}[kind(item)]


def softmax_top(scores: list[float]) -> float:
    import math
    m = max(scores)
    e = [math.exp(s - m) for s in scores]
    return max(e) / sum(e)


def run(engine: str, decide, tasks=TASKS, prepare=None):
    """Run `decide(item) -> {ranking, confidence}` over the tasks; failures become rows, never skipped."""
    RESULTS.mkdir(exist_ok=True)
    for task in tasks:
        its = items(task)
        if prepare:
            prepare(task, its)
        path = RESULTS / f"{engine}.{task}.jsonl"
        # Rows go to a .part file as they come, so a run cut by a time box resumes where it stopped.
        part = path.with_suffix(".part")
        lines = part.read_text(encoding="utf-8").splitlines() if part.exists() else []
        done = {json.loads(x)["id"] for x in lines}
        for it in its:
            if it["id"] in done:
                continue
            t0 = time.perf_counter()
            try:
                ans = decide(it)
                row = {"ranking": list(ans["ranking"]), "confidence": float(ans.get("confidence", 0.0)),
                       **{k: v for k, v in ans.items() if k not in ("ranking", "confidence")}}
            except Exception as e:     # recorded, so a failing engine shows up as a row, not a gap
                row = {"ranking": [], "confidence": 0.0, "error": f"{type(e).__name__}: {e}"[:300]}
                traceback.print_exc(file=sys.stderr)
            row.update(id=it["id"], split=it["split"], gold=it["gold"], latency_s=time.perf_counter() - t0)
            lines.append(json.dumps(row))
            with part.open("a", encoding="utf-8") as f:
                f.write(lines[-1] + "\n")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        part.unlink(missing_ok=True)
        rows = [json.loads(x) for x in lines]
        ok = sum(1 for r in rows if r["ranking"][:1] and r["ranking"][0] in r["gold"])
        print(f"{engine} {task}: top-1 {ok}/{len(rows)}, errors {sum('error' in r for r in rows)}, "
              f"median {statistics.median(r['latency_s'] for r in rows) * 1000:.0f} ms", flush=True)
