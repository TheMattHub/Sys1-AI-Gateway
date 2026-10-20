"""Teacher labels on TRAIN2 over all 90 tools: `python distill/label.py harrier|gemma4|haiku`.

Same item as the bench's "Tall" (common.question, the 90 tool documents as find_tool indexes them). harrier
(bench venv) gives the top-20 shortlist Gemma needs (its letter limit, as in round 2); gemma4 (bench venv,
Ollama) ranks that shortlist; haiku (Python312, eng_anthropic) ranks all 90. One JSON line per request in
distill/labels/<teacher>.jsonl, appended as it goes: a rerun skips the ids already there (resumable)."""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import common  # noqa: E402

OUT = HERE / "labels"


def items():
    tools = json.loads((HERE / "derived" / "tools.json").read_text(encoding="utf-8"))
    rows = [json.loads(x) for x in (HERE / "train2.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return [{"id": r["id"], "task": "Tall", "split": r["split"], "text": r["query"], "options": list(tools),
             "docs": {n: t["doc"] for n, t in tools.items()}, "summaries": {n: t["summary"] for n, t in tools.items()},
             "gold": r["gen_gold"]} for r in rows]


def load(name):
    p = OUT / f"{name}.jsonl"
    return {r["id"]: r for r in map(json.loads, p.read_text(encoding="utf-8").splitlines())} if p.exists() else {}


def main(name):
    its = items()
    if name == "harrier":
        import eng_hf
        decide, keep = eng_hf.bi(), 20
    elif name == "gemma4":
        import eng_gateway
        from system1_gateway.providers.ollama import OllamaProvider
        short = load("harrier")
        for it in its:
            eng_gateway._short[("Tall", it["id"])] = short[it["id"]]["ranking"]
        decide, keep = eng_gateway.via_provider(OllamaProvider({"model": "hf.co/unsloth/gemma-4-E4B-it-GGUF:Q4_K_M"})), 3
    else:
        import eng_anthropic
        decide, keep = eng_anthropic.make(eng_anthropic.MODELS[name]), 3
    OUT.mkdir(exist_ok=True)
    done = load(name)
    with (OUT / f"{name}.jsonl").open("a", encoding="utf-8") as f:
        for i, it in enumerate(its):
            if it["id"] in done:
                continue
            t0 = time.perf_counter()
            try:
                ans = decide(it)
                row = {"ranking": list(ans["ranking"])[:keep],
                       **{k: v for k, v in ans.items() if k in ("tokens_in", "tokens_out")}}
            except Exception as e:     # a failed row is retried on the next run, not kept
                print(f"{it['id']}: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr, flush=True)
                if name == "haiku" and "rate" in str(e).lower():
                    time.sleep(60)
                continue
            row.update(id=it["id"], latency_s=time.perf_counter() - t0)
            f.write(json.dumps(row) + "\n")
            f.flush()
            if i % 100 == 0:
                print(name, i, flush=True)
    print(name, "labelled", len(load(name)), "of", len(its), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
