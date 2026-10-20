"""Laya, Von and Gemma 4 E4B through the System-1 gateway's own adapters (stdlib; any Python 3.12):
`python eng_gateway.py laya|von|gemma4`. The servers must be running (run.ps1 starts and stops them).

Each is asked once per decision in its native choice form, with the same instruction (common.question):
Laya and Gemma get the label documents as options (mapped back to labels), Von gets {label: document}.
Laya takes at most 20 options and the Ollama adapter 26 letters, so B's label sets are shortlisted to the
B bi-encoder baseline's top 20 (results/harrier-bi.<task>.jsonl); T's 10 candidates go as they are."""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from system1_gateway.providers.http import LocalHTTP                  # noqa: E402
from system1_gateway.providers.laya import LayaProvider               # noqa: E402
from system1_gateway.providers.ollama import OllamaProvider           # noqa: E402
from system1_gateway.schema import DecideRequest                      # noqa: E402

import common                                                          # noqa: E402

TIMEOUT = 120
CAP = 20
_short = {}


def prepare(task, its):
    if len(its[0]["options"]) <= CAP:
        return
    path = common.RESULTS / f"harrier-bi.{task}.jsonl"
    rows = {json.loads(x)["id"]: json.loads(x)["ranking"] for x in path.read_text(encoding="utf-8").splitlines() if x}
    for it in its:
        _short[(task, it["id"])] = rows[it["id"]][:CAP]


def options(it, shortlist=True):
    """Laya takes at most CAP options: the harrier top CAP when there are more. Von (shortlist=False) gets all
    of them in round 2 (round 1 shortlisted its B sets too)."""
    return _short.get((it["task"], it["id"]), it["options"]) if shortlist else it["options"]


def ranked(probs: dict, back: dict) -> dict:
    order = sorted(probs, key=lambda k: -probs[k])
    return {"ranking": [back[k] for k in order], "confidence": probs[order[0]]}


def via_provider(provider):
    def decide(it):
        opts = options(it)
        back = {it["docs"][o]: o for o in opts}
        req = DecideRequest(question=common.question(it), request_id=uuid.uuid4().hex,
                            options=list(back), context={"task": it["text"]})
        ans = provider.decide(req, TIMEOUT)
        if ans.get("abstain"):
            raise RuntimeError(f"abstained: {ans.get('rationale')}")
        return ranked(ans["probabilities"], back)
    return decide


def von():
    http = LocalHTTP("Von", "http://127.0.0.1:8777")

    def decide(it):
        opts = options(it, shortlist=not common.R2)
        body = {"model": "von-1.3", "state": {"task": it["text"]},
                "questions": {"decision": {"type": "choice", "instructions": common.question(it),
                                           "criteria": {o: it["docs"][o] for o in opts}}}}
        ans = http.call("POST", "/v1/systemone", body, TIMEOUT)["answers"]["decision"]
        return ranked(ans["probabilities"], {o: o for o in opts})
    return decide


if __name__ == "__main__":
    name = sys.argv[1]
    make = {"laya": lambda: via_provider(LayaProvider({"model": "typed-decisions"})),
            "von": von,
            "gemma4": lambda: via_provider(OllamaProvider({"model": "hf.co/unsloth/gemma-4-E4B-it-GGUF:Q4_K_M"}))}[name]
    common.run(name, make(), prepare=prepare)
