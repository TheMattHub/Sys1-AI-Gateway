"""Liquid AI d1 decision models through llama.cpp's `llama-server` (stdlib; any Python 3.12):
`python eng_d1.py d1-omni|d1-3b [endpoint]`. The server must be running with the model (run.ps1 starts it).

d1-omni  LiquidAI/d1-omni-600M-GGUF, F16 (the card's float16 path, text only)
d1-3b    LiquidAI/d1-3B-GGUF, Q8_0 (its float16 weights, 6.2 GB, do not fit the 4 GB GPU)
Both answer the TypeSafe-style POST /v1/systemone (as Von does): one `choice` question per decision, the
instruction from common.question, criteria {label: label document}. llama-server takes up to 255 options,
so every task goes as it is, all 90 tools included. Licence: LFM Open License v1.0 (commercial use only
below USD 10 M annual revenue)."""
import json
import sys
import urllib.request

import common

TIMEOUT = 120


def systemone(endpoint, model=None, shortlist=None):
    """decide() for any /v1/systemone server; `shortlist(it)` limits the options (e.g. Ollama's 26)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))    # loopback, never via a proxy

    def decide(it):
        opts = shortlist(it) if shortlist else it["options"]
        body = {"state": it["text"], "questions": {"decision": {
            "type": "choice", "instructions": common.question(it), "criteria": {o: it["docs"][o] for o in opts}}}}
        if model:
            body["model"] = model
        req = urllib.request.Request(endpoint.rstrip("/") + "/v1/systemone", json.dumps(body).encode("utf-8"),
                                     {"Content-Type": "application/json"})
        with opener.open(req, timeout=TIMEOUT) as r:
            ans = json.loads(r.read())["answers"]["decision"]
        probs = ans["probabilities"]
        order = sorted(probs, key=lambda k: -probs[k])
        return {"ranking": order, "confidence": probs[order[0]]}
    return decide


if __name__ == "__main__":
    name = sys.argv[1]
    assert name in ("d1-omni", "d1-3b"), name
    common.run(name, systemone(sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8790"))
