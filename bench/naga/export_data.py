"""Export the engine-side data the bench needs (run with a Python with naga's dependencies, PYTHONPATH=a naga clone).

Writes derived/tools.json (tool docs), derived/tool_queries.json (TRAIN/TEST with find_tool's top 10),
derived/blocks.json and derived/distributions.json (label descriptions). The engine is only read."""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAGA = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[2] / "naga"
sys.path.insert(0, str(NAGA / "tests"))

from nagasim import toolsearch                                       # noqa: E402
from nagasim.agent_tools.core import TOOLS, _first_sentence          # noqa: E402
from nagasim.agent_tools.discover import catalogue_index
from nagasim.agent_tools.reference import list_block_types, list_distributions             # noqa: E402
from nagasim.core.block_registry import BLOCK_REGISTRY               # noqa: E402
from nagasim.core.distributions import DISTRIBUTION_REGISTRY         # noqa: E402
import test_toolsearch as tt                                         # noqa: E402

OUT = HERE / ("derived2" if os.environ.get("BENCH_ROUND") == "2" else "derived")
OUT.mkdir(exist_ok=True)


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=1, ensure_ascii=True), encoding="utf-8")


# Tool documents: name + the summary find_tool indexes + argument docs (the "args" field it indexes).
tools = {}
for t in TOOLS.values():
    props = (t.input_schema or {}).get("properties") or {}
    args = "; ".join(f"{k}: {v.get('description', '')}".strip() for k, v in props.items())
    summary = toolsearch._summary(t.description or "")
    tools[t.name] = {"summary": summary, "doc": f"{t.name}: {summary}" + (f" Arguments: {args}" if args else "")}
dump("tools.json", tools)

idx = catalogue_index()
splits = {"TRAIN": tt.EVAL + tt.HELD_OUT, "TEST": tt.HELD_OUT_2}
rows = {}
for split, table in splits.items():
    rows[split] = [{"query": q, "gold": sorted(g),
                    "candidates": [c["name"] for c in toolsearch.search(idx, q, limit=10)],
                    "ranked_all": [c["name"] for c in toolsearch.search(idx, q, limit=len(TOOLS))]} for q, g in table]
dump("tool_queries.json", rows)

# Synthetic tuning queries made from the tool descriptions only (never from a TEST row): each later sentence
# of a description ("Use it when ...") as a query for its tool, with find_tool's top 10 as hard negatives.
import re  # noqa: E402
synth = []
for t in TOOLS.values():
    body = " ".join((t.description or "")[len(toolsearch._summary(t.description or "")):].split())
    for s in re.split(r"(?<=[.!?])\s", body):
        if 30 <= len(s) <= 200 and not s.startswith(("Returns", "Example", "Answers")) and "{" not in s:
            synth.append({"query": s, "gold": [t.name],
                          "candidates": [c["name"] for c in toolsearch.search(idx, s, limit=10)],
                          "ranked_all": [c["name"] for c in toolsearch.search(idx, s, limit=len(TOOLS))]})
dump("tool_synth.json", synth)

skip = {"SUBMODEL", "SUB_ENTRY", "SUB_EXIT"}
# Block docstrings past the first sentence, for synthetic B pairs (label descriptions, not test rows).
dump("blocks_synth.json", {n: [s for s in re.split(r"(?<=[.!?])\s", " ".join((sp.cls.__doc__ or "").split()))[1:4]
                               if 30 <= len(s) <= 200]
                           for n, sp in sorted(BLOCK_REGISTRY.items()) if n not in skip})
# The label texts are what the engine's own list tools say (round 2: the fuller summaries).
dump("blocks.json", {b["type"]: b["summary"] for b in list_block_types()["block_types"] if b["type"] not in skip})
dump("distributions.json", {d["name"]: d["summary"] for d in list_distributions()["distributions"]})
print(f"tools {len(tools)}, TRAIN {len(rows['TRAIN'])}, TEST {len(rows['TEST'])}, "
      f"blocks {len(BLOCK_REGISTRY) - len(skip & set(BLOCK_REGISTRY))}, distributions {len(DISTRIBUTION_REGISTRY)}")
