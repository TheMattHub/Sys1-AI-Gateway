"""Baseline: find_tool's own order for T; for B the engine's BM25 tool search over the label documents
(plain token overlap). Run with ArenaPy's Python312 and PYTHONPATH=ArenaPy. Confidence = top score's share
of the top two (a score margin; BM25 scores are not probabilities)."""
from nagasim import toolsearch
from nagasim.agent_tools.discover import catalogue_index

import common

_idx = {}


def prepare(task, its):
    if task not in ("T", "Tall"):
        it = its[0]
        if task == "fields":     # one index per context: the label set differs
            for ctx in {i["context"] for i in its}:
                one = next(i for i in its if i["context"] == ctx)
                _idx[ctx] = toolsearch.index([{"name": o, "description": one["docs"][o]} for o in one["options"]])
        else:
            _idx[task] = toolsearch.index([{"name": o, "description": it["docs"][o]} for o in it["options"]])


def decide(it):
    idx = catalogue_index() if common.kind(it) == "T" else _idx[it.get("context") or it["task"]]
    found = toolsearch.search(idx, it["text"], limit=len(it["options"]))
    ranking = [f["name"] for f in found]
    ranking += [o for o in it["options"] if o not in ranking]        # unmatched labels keep their order
    s = [f["score"] for f in found[:2]] + [0.0, 0.0]
    conf = s[0] / (s[0] + s[1]) if s[0] > 0 else 0.0
    return {"ranking": ranking, "confidence": conf}


if __name__ == "__main__":
    common.run("baseline", decide, prepare=prepare)
