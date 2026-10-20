"""Build the distillation data (Python with naga's dependencies, PYTHONPATH=a naga clone):
`python distill/prep.py <train2 part files...>`.

TRAIN2: the generated requests (a Claude Sonnet subagent per 30 tools, from the tool descriptions and the TRAIN
queries only), exact duplicates and near-duplicates removed, then every near-copy of a TEST2 or HELD_OUT_2 row
dropped. Near = word-set Jaccard >= NEAR. A seeded 10% of TRAIN2 is held out (split "held") for the student check.
Writes distill/train2.jsonl and distill/derived/{tools.json, tool_queries.json} (TEST2 and HELD_OUT_2 with
find_tool's top 10 and full order), so common.py's T/Tall items work on them with BENCH_ROUND=distill."""
import json
import random
import re
import shutil
import sys
from pathlib import Path

from nagasim import toolsearch
from nagasim.agent_tools.discover import catalogue_index

HERE = Path(__file__).resolve().parent
NEAR, SEED = 0.6, 0


def words(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def jac(a, b):
    return len(a & b) / max(1, len(a | b))


def find(idx, q):
    ranked = [c["name"] for c in toolsearch.search(idx, q, limit=90)]
    return {"candidates": ranked[:10], "ranked_all": ranked}


def main(parts):
    idx = catalogue_index()
    test2 = [json.loads(x) for x in (HERE / "test2.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    held2 = json.loads((HERE.parent / "derived2" / "tool_queries.json").read_text(encoding="utf-8"))["TEST"]
    blind = [words(r["query"]) for r in test2 + held2]

    rows = [json.loads(x) for p in parts for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]
    kept, seen, n_dup, n_blind = [], [], 0, 0
    for r in rows:
        w = words(r["query"])
        if any(jac(w, b) >= NEAR for b in blind):
            n_blind += 1
            continue
        if any(jac(w, s) >= NEAR for s in seen):
            n_dup += 1
            continue
        seen.append(w)
        kept.append({"query": r["query"], "gen_gold": sorted(r["gold"]), **find(idx, r["query"])})
    rng = random.Random(SEED)
    held = set(rng.sample(range(len(kept)), len(kept) // 10))
    for i, r in enumerate(kept):
        r["id"], r["split"] = f"TRAIN2-{i}", "held" if i in held else "fit"
    (HERE / "train2.jsonl").write_text("".join(json.dumps(r) + "\n" for r in kept), encoding="utf-8")

    der = HERE / "derived"
    der.mkdir(exist_ok=True)
    shutil.copy(HERE.parent / "derived2" / "tools.json", der / "tools.json")
    q = {"TEST2": [{"query": r["query"], "gold": sorted(r["gold"]), **find(idx, r["query"])} for r in test2],
         "HELD_OUT_2": held2}
    (der / "tool_queries.json").write_text(json.dumps(q, indent=1), encoding="utf-8")
    print(json.dumps({"generated": len(rows), "near_dup_dropped": n_dup, "near_blind_dropped": n_blind,
                      "train2": len(kept), "held": len(held), "tools": len({g for r in kept for g in r["gen_gold"]})}))


if __name__ == "__main__":
    main(sys.argv[1:])
