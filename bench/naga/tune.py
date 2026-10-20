"""Fine-tune the gte-reranker-modernbert-base cross-encoder on TRAIN + synthetic pairs only (bench venv).

Training groups: one query, its right document first, then hard negatives (the other find_tool top-10
candidates for T; the other labels for the block-docstring pairs). Loss: softmax cross-entropy over the
group (listwise, matches re-ranking). Sources: T TRAIN (EVAL + HELD_OUT), derived/tool_synth.json (later
sentences of each tool description as queries), derived/blocks_synth.json (block docstrings). Never a TEST row.

Step 1, the honest check: 2-fold cross-validation on T TRAIN grouped by gold tool (a fold never sees its
tools' queries), zero-shot vs tuned top-1 on the held-out fold. Step 2: train on all of it, save
models/tuned, then measure every task once (results/tuned.*.jsonl): T TEST is read here for the first time."""
import json
import random
import sys

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

import common

MID = "Alibaba-NLP/gte-reranker-modernbert-base"
SEED, EPOCHS, LR, ACCUM, MAXLEN, NEG = 0, 2, 2e-5, 4, 256, 9
DEV = "cuda"


def groups_t(rows, docs, rng):
    """Two groups per (query, gold): find_tool's top-10 negatives (mode top10) and, for mode "all", the
    top 5 of those plus 4 drawn from the rest of the 90 (find_tool's ranks 11-90)."""
    out = []
    for r in rows:
        for g in r["gold"]:
            negs = [c for c in r["candidates"] if c not in r["gold"]][:NEG]
            if negs:
                out.append((r["query"], [docs[g]] + [docs[n] for n in negs]))
            rest = [c for c in r.get("ranked_all", []) if c not in r["candidates"] and c not in r["gold"]]
            if len(rest) >= 4:
                out.append((r["query"], [docs[g]] + [docs[n] for n in negs[:5] + rng.sample(rest, 4)]))
    return out


def groups_blocks(rng):
    labels = json.loads((common.DERIVED / "blocks.json").read_text(encoding="utf-8"))
    docs = {k: f"{k}: {v}" for k, v in labels.items()}
    out = []
    for name, sents in json.loads((common.DERIVED / "blocks_synth.json").read_text(encoding="utf-8")).items():
        for s in sents:
            negs = rng.sample([d for k, d in docs.items() if k != name], NEG)
            out.append((s, [docs[name]] + negs))
    return out


def train(groups, rng):
    torch.manual_seed(SEED)
    tok = AutoTokenizer.from_pretrained(MID)
    model = AutoModelForSequenceClassification.from_pretrained(MID, num_labels=1).to(DEV)
    model.gradient_checkpointing_enable()
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    steps = EPOCHS * len(groups) // ACCUM
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / max(1, steps // 10)) * max(0.0, 1 - s / max(1, steps)))
    model.train()
    for epoch in range(EPOCHS):
        order = groups[:]
        rng.shuffle(order)
        total = 0.0
        for i, (q, docs) in enumerate(order):
            enc = tok([q] * len(docs), docs, truncation=True, max_length=MAXLEN, padding=True, return_tensors="pt").to(DEV)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(**enc).logits.view(1, -1).float()
            loss = torch.nn.functional.cross_entropy(logits, torch.zeros(1, dtype=torch.long, device=DEV)) / ACCUM
            loss.backward()
            total += loss.item() * ACCUM
            if (i + 1) % ACCUM == 0 or i + 1 == len(order):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step(); sched.step(); opt.zero_grad()
        print(f"epoch {epoch}: mean loss {total / len(order):.3f}", flush=True)
    model.eval()
    return tok, model


def scorer(tok, model):
    @torch.no_grad()
    def score(q, docs):
        out = []
        for i in range(0, len(docs), 30):     # 90 documents at once would not fit the 4 GB GPU with padding
            part = docs[i:i + 30]
            enc = tok([q] * len(part), part, truncation=True, max_length=MAXLEN, padding=True, return_tensors="pt").to(DEV)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                out += model(**enc).logits.view(-1).float().tolist()
        return out
    return score


def top1(score, rows, docs, key="candidates"):
    hit = 0
    for r in rows:
        cands = r[key] if key == "candidates" else list(docs)
        s = score(r["query"], [docs[c] for c in cands])
        best = cands[max(range(len(s)), key=s.__getitem__)]
        hit += best in r["gold"]
    return hit


def main():
    rng = random.Random(SEED)
    tools = json.loads((common.DERIVED / "tools.json").read_text(encoding="utf-8"))
    docs = {k: v["doc"] for k, v in tools.items()}
    train_rows = json.loads((common.DERIVED / "tool_queries.json").read_text(encoding="utf-8"))["TRAIN"]
    synth = json.loads((common.DERIVED / "tool_synth.json").read_text(encoding="utf-8"))
    extra = groups_t(synth, docs, rng) + groups_blocks(rng)

    # Step 1: 2-fold CV on TRAIN, grouped by gold tool (its synthetic pairs stay in: they are not TRAIN rows).
    tools_in = sorted({r["gold"][0] for r in train_rows})
    random.Random(SEED).shuffle(tools_in)
    folds = [set(tools_in[0::2]), set(tools_in[1::2])]
    tok0 = AutoTokenizer.from_pretrained(MID)
    m0 = AutoModelForSequenceClassification.from_pretrained(MID, num_labels=1).to(DEV).eval()
    cv = {"zero_shot": 0, "tuned": 0, "zero_shot_all": 0, "tuned_all": 0, "n": 0}
    for k, held in enumerate(folds):
        test_rows = [r for r in train_rows if r["gold"][0] in held]
        fit_rows = [r for r in train_rows if r["gold"][0] not in held]
        cv["zero_shot"] += top1(scorer(tok0, m0), test_rows, docs)
        cv["zero_shot_all"] += top1(scorer(tok0, m0), test_rows, docs, "all")
        tok, model = train(groups_t(fit_rows, docs, rng) + extra, rng)
        cv["tuned"] += top1(scorer(tok, model), test_rows, docs)
        cv["tuned_all"] += top1(scorer(tok, model), test_rows, docs, "all")
        cv["n"] += len(test_rows)
        del model; torch.cuda.empty_cache()
        print(f"fold {k}: {cv}", flush=True)
    del m0; torch.cuda.empty_cache()
    common.RESULTS.mkdir(exist_ok=True)
    (common.RESULTS / "tune_cv.json").write_text(json.dumps(cv), encoding="utf-8")

    # Step 2: train on everything allowed, save, measure once.
    tok, model = train(groups_t(train_rows, docs, rng) + extra, rng)
    out = common.HERE / "models" / ("tuned2" if common.R2 else "tuned")
    model.save_pretrained(out); tok.save_pretrained(out)
    score = scorer(tok, model)

    def decide(it):
        s = score(it["text"], [it["docs"][o] for o in it["options"]])
        order = sorted(range(len(s)), key=lambda i: -s[i])
        return {"ranking": [it["options"][i] for i in order], "confidence": common.softmax_top(s)}
    common.run("tuned", decide)


if __name__ == "__main__":
    sys.exit(main())
