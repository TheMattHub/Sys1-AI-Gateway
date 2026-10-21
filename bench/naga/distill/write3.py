"""TEST3, a blind multi-writer test set: `python distill/write3.py <writer>` then `python distill/write3.py build`.

Four writers, about 40 requests each, every one seeing ONLY the 90 tool names (no descriptions, no existing
queries) and the target tool; the target is the gold. opus (Claude Opus 5.5, API, eng_anthropic's key path;
Python312), gemma4 (Gemma 4 E4B, Ollama), d1-3b (LiquidAI d1-3B Q8_0, llama-server on 8790; it writes plain text
through /v1/chat/completions), qwen3 (Qwen/Qwen3-1.7B, the base AnyJev used, 4-bit NF4, transformers; bench venv).
Targets: a seeded shuffle of the 90 tools plus 70 more, dealt to the writers in turn; the asked length rotates
(short, one sentence, two or three sentences). A cheap sanity pass on each answer drops it, logged, and asks again
(at most 3 tries): an underscore tool name in the text (single-word names such as undo or export are plain English
and stay), or not a request (under 3 or over 90 words, a preamble such as "Here is"). Raw rows go to
distill/test3_raw/<writer>.jsonl, appended (resumable). build: near-duplicates of TEST2, HELD_OUT_2, TRAIN2 or an
earlier TEST3 row are dropped (word-set Jaccard >= 0.6, as prep.py), every drop goes to distill/test3_drops.jsonl,
the rest to distill/test3.jsonl."""
import json
import random
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "test3_raw"
WRITERS = {"opus": "Claude Opus 5.5", "gemma4": "Gemma 4 E4B", "qwen3": "Qwen3-1.7B", "d1-3b": "LiquidAI d1-3B"}
TOOLS = list(json.loads((HERE / "derived" / "tools.json").read_text(encoding="utf-8")))
STYLES = ["very short, 3 to 8 words, the way people type in a hurry",
          "one plain sentence",
          "two or three sentences: a little context about your project, then what you want"]
SEED, NEAR, TRIES = 3, 0.6, 3
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def targets():
    rng = random.Random(SEED)
    a, b = TOOLS[:], TOOLS[:]
    rng.shuffle(a)
    rng.shuffle(b)
    order = a + b[:70]
    return {w: [(i, order[i]) for i in range(k, len(order), len(WRITERS))] for k, w in enumerate(WRITERS)}


def prompt(target, style):
    return ("A desktop simulation tool (discrete-event, system dynamics and digital-twin models of factories, "
            "warehouses and logistics) has an AI assistant. The assistant can call these 90 tools; you see only "
            f"their names:\n{', '.join(TOOLS)}\n\n"
            f"Write one request that a user of the tool might type to the assistant, which the assistant should "
            f"handle by calling the tool `{target}`. Write it as the user would: plain everyday language about "
            f"their own work, not about tools; never write a tool name. Length: {style}. "
            "Reply with the request only, no quotes, no explanation.")


def clean(text):
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    t = re.sub(r"^(request|user)\s*:\s*", "", t, flags=re.I)
    t = " ".join(t.split()).strip().strip('"“”\'').strip()
    return t


def problem(t):
    if any(n in t for n in TOOLS if "_" in n):
        return "names a tool verbatim"
    n = len(t.split())
    if n < 3 or n > 90 or re.match(r"(here|sure|certainly|okay|of course)\b", t, re.I):
        return "not a request"
    return None


def _post(url, body, timeout=180):
    req = urllib.request.Request(url, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    with NO_PROXY.open(req, timeout=timeout) as r:
        return json.loads(r.read())


def backend(writer):
    if writer == "opus":
        sys.path.insert(0, str(HERE.parent))
        import anthropic
        import eng_anthropic
        client = anthropic.Anthropic(api_key=eng_anthropic._key(), max_retries=6)

        def gen(p):
            r = client.messages.create(model="claude-opus-5-5", max_tokens=300, messages=[{"role": "user", "content": p}])
            return "".join(b.text for b in r.content if b.type == "text"), {"tokens_in": r.usage.input_tokens,
                                                                             "tokens_out": r.usage.output_tokens}
        return gen
    if writer == "gemma4":
        def gen(p):
            r = _post("http://127.0.0.1:11434/api/chat", {
                "model": "hf.co/unsloth/gemma-4-E4B-it-GGUF:Q4_K_M", "stream": False, "think": False,
                "messages": [{"role": "user", "content": p}], "options": {"temperature": 0.8, "num_predict": 200}})
            return r["message"]["content"], {}
        return gen
    if writer == "d1-3b":
        def gen(p):
            r = _post("http://127.0.0.1:8790/v1/chat/completions", {
                "messages": [{"role": "user", "content": p}], "max_tokens": 200, "temperature": 0.8})
            return r["choices"][0]["message"]["content"], {}
        return gen
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    torch.manual_seed(SEED)
    mid = "Qwen/Qwen3-1.7B"
    tok = AutoTokenizer.from_pretrained(mid)
    model = AutoModelForCausalLM.from_pretrained(mid, device_map="cuda", quantization_config=BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)).eval()

    @torch.no_grad()
    def gen(p):
        text = tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True,
                                       enable_thinking=False)
        enc = tok(text, return_tensors="pt").to("cuda")
        out = model.generate(**enc, max_new_tokens=200, do_sample=True, temperature=0.8, top_p=0.95)
        return tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True), {}
    return gen


def write(writer):
    RAW.mkdir(exist_ok=True)
    path = RAW / f"{writer}.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    done = {r["slot"] for r in rows if r["kept"]}
    tried = {}
    for r in rows:
        tried[r["slot"]] = tried.get(r["slot"], 0) + 1
    gen = None
    with path.open("a", encoding="utf-8") as f:
        for slot, target in targets()[writer]:
            while slot not in done and tried.get(slot, 0) < TRIES:
                gen = gen or backend(writer)
                raw, usage = gen(prompt(target, STYLES[slot % 3]))
                q = clean(raw)
                why = problem(q)
                tried[slot] = tried.get(slot, 0) + 1
                f.write(json.dumps({"slot": slot, "writer": writer, "target": target, "style": slot % 3,
                                    "raw": raw, "query": q, "kept": why is None, "drop": why, **usage}) + "\n")
                f.flush()
                if why is None:
                    done.add(slot)
    print(writer, len(done), "of", len(targets()[writer]), flush=True)


def words(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def jac(a, b):
    return len(a & b) / max(1, len(a | b))


def build():
    q = json.loads((HERE / "derived" / "tool_queries.json").read_text(encoding="utf-8"))
    train = [json.loads(x)["query"] for x in (HERE / "train2.jsonl").read_text(encoding="utf-8").splitlines()]
    old = [(s, words(r["query"])) for s in ("TEST2", "HELD_OUT_2") for r in q[s]] + [("TRAIN2", words(t)) for t in train]
    raw = sorted((json.loads(x) for w in WRITERS for x in (RAW / f"{w}.jsonl").read_text(encoding="utf-8").splitlines()),
                 key=lambda r: r["slot"])
    keep, drops, seen = [], [], []
    for r in raw:
        if not r["kept"]:
            drops.append({**r, "stage": "sanity"})
            continue
        w = words(r["query"])
        near = next((s for s, b in old if jac(w, b) >= NEAR), None) or ("TEST3" if any(jac(w, s) >= NEAR for s in seen) else None)
        if near:
            drops.append({**r, "stage": "dedupe", "drop": f"near-copy of a {near} row"})
            continue
        seen.append(w)
        keep.append({"query": r["query"], "gold": [r["target"]], "writer": WRITERS[r["writer"]]})
    (HERE / "test3.jsonl").write_text("".join(json.dumps(r) + "\n" for r in keep), encoding="utf-8")
    (HERE / "test3_drops.jsonl").write_text("".join(json.dumps(d) + "\n" for d in drops), encoding="utf-8")
    per = {w: sum(r["writer"] == w for r in keep) for w in WRITERS.values()}
    print(json.dumps({"kept": len(keep), "per_writer": per, "tools": len({r["gold"][0] for r in keep}),
                      "drops": {s: sum(d["stage"] == s for d in drops) for s in ("sanity", "dedupe")}}))


SEEDED = ("baseline", "harrier-bi", "gte-rerank", "gte-gemma4", "gte-haiku", "gemma4", "haiku", "d1-3b")


def derive():
    """BENCH_ROUND=test3 data (Python with naga's dependencies, PYTHONPATH=a naga clone): derived3 = TEST3 with
    find_tool's top 10 and full order, plus TEST2 and HELD_OUT_2 as they were; the TEST2/HELD_OUT_2 rows of the
    engines run before are copied to results3/<engine>.<task>.part, so their runs only add TEST3."""
    import shutil
    from nagasim import toolsearch
    from nagasim.agent_tools.discover import catalogue_index
    idx = catalogue_index()

    def find(q):
        ranked = [c["name"] for c in toolsearch.search(idx, q, limit=90)]
        return {"candidates": ranked[:10], "ranked_all": ranked}
    old = json.loads((HERE / "derived" / "tool_queries.json").read_text(encoding="utf-8"))
    same = sum(find(r["query"])["candidates"] == r["candidates"] for r in old["TEST2"])
    rows = [json.loads(x) for x in (HERE / "test3.jsonl").read_text(encoding="utf-8").splitlines()]
    der = HERE / "derived3"
    der.mkdir(exist_ok=True)
    shutil.copy(HERE / "derived" / "tools.json", der / "tools.json")
    q = {"TEST3": [{"query": r["query"], "gold": r["gold"], "writer": r["writer"], **find(r["query"])} for r in rows], **old}
    (der / "tool_queries.json").write_text(json.dumps(q, indent=1), encoding="utf-8")
    res = HERE / "results3"
    res.mkdir(exist_ok=True)
    for e in SEEDED:
        for t in ("T", "Tall"):
            src = HERE / "results" / f"{e}.{t}.jsonl"
            if src.exists() and not (res / f"{e}.{t}.jsonl").exists():
                shutil.copy(src, res / f"{e}.{t}.part")
    print(f"TEST2 find_tool top 10 unchanged on {same}/{len(old['TEST2'])}; TEST3 gold in find_tool's top 10:",
          sum(r["gold"][0] in x["candidates"] for r, x in zip(rows, q["TEST3"])), "of", len(rows))


if __name__ == "__main__":
    {"build": build, "derive": derive}.get(sys.argv[1], lambda: write(sys.argv[1]))()
