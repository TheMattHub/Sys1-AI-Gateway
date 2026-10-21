"""Train one gte student per teacher on TRAIN2 (bench venv): `python distill/train.py gemma4|haiku|opus|agreed`.

tune.py's recipe as it is (cross-encoder, listwise loss, find_tool's top 10 and ranks 11-90 as hard negatives,
2 epochs, lr 2e-5, seed 0, one run each). Positive = the teacher's top-1; its 2nd and 3rd picks are left out of the
negatives (tune.py's loss takes one positive, so no soft positives). "agreed" (no teacher of its own): the rows
where Haiku's top-1 is the generated tool and, when Opus labels exist, Opus's top-1 is too; positive = that tool,
both teachers' other top-3 picks left out of the negatives. Fits on the 90% "fit" split; then the 10% "held" split
is scored over all 90 tools: agreement with the teacher's top-1 and with the generated gold. Saves
distill/models/gte-<teacher> (not committed) and distill/results/train_<teacher>.json.

Resumable (round 4): a call trains for at most BUDGET seconds, then saves model, optimiser, scheduler and RNG states
to distill/models/ckpt-<teacher> and exits with code 3; the next call goes on from there, so the run matches one
uninterrupted tune.train (same loop, same order). Repeat until it prints the result."""
import json
import random
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import tune  # noqa: E402

BUDGET = 480


def labels(teacher, rows):
    def load(t):
        p = HERE / "labels" / f"{t}.jsonl"
        return {r["id"]: r["ranking"] for r in map(json.loads, p.read_text(encoding="utf-8").splitlines())} if p.exists() else None
    if teacher != "agreed":
        return {i: (lab[0], set(lab[:3])) for i, lab in load(teacher).items() if lab}
    haiku, opus = load("haiku"), load("opus")
    out = {}
    for i, r in rows.items():
        h, o = haiku.get(i) or [None], (opus.get(i) or [None]) if opus else None
        if h[0] in r["gen_gold"] and (o is None or o[0] == h[0]):
            out[i] = (h[0], set(h[:3]) | set((o or [])[:3]))
    return out


def train(groups, rng, ckpt):
    """tune.train, cut into BUDGET-second calls; returns (tok, model) when done, else saves and exits 3."""
    t_start = time.perf_counter()
    torch.manual_seed(tune.SEED)
    tok = AutoTokenizer.from_pretrained(tune.MID)
    model = AutoModelForSequenceClassification.from_pretrained(tune.MID, num_labels=1).to(tune.DEV)
    model.gradient_checkpointing_enable()
    opt = torch.optim.AdamW(model.parameters(), lr=tune.LR, weight_decay=0.01)
    steps = tune.EPOCHS * len(groups) // tune.ACCUM
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / max(1, steps // 10)) * max(0.0, 1 - s / max(1, steps)))
    state, before = {"epoch": 0, "i": 0, "order": None, "total": 0.0}, 0.0
    if (ckpt / "state.pt").exists():
        s = torch.load(ckpt / "state.pt", weights_only=False)
        model.load_state_dict(s["model"]); opt.load_state_dict(s["opt"]); sched.load_state_dict(s["sched"])
        rng.setstate(s["rng"]); torch.set_rng_state(s["torch_rng"]); torch.cuda.set_rng_state(s["cuda_rng"])
        state, before = s["state"], s["minutes"]
        print(f"resumed at epoch {state['epoch']}, group {state['i']}", flush=True)
    model.train()
    for epoch in range(state["epoch"], tune.EPOCHS):
        if state["order"] is None:
            order = groups[:]
            rng.shuffle(order)
            state.update(order=order, total=0.0, i=0)
        order = state["order"]
        for i in range(state["i"], len(order)):
            q, docs = order[i]
            enc = tok([q] * len(docs), docs, truncation=True, max_length=tune.MAXLEN, padding=True, return_tensors="pt").to(tune.DEV)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(**enc).logits.view(1, -1).float()
            loss = torch.nn.functional.cross_entropy(logits, torch.zeros(1, dtype=torch.long, device=tune.DEV)) / tune.ACCUM
            loss.backward()
            state["total"] += loss.item() * tune.ACCUM
            if (i + 1) % tune.ACCUM == 0 or i + 1 == len(order):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step(); sched.step(); opt.zero_grad()
                # Checkpoint only at an optimiser step (no half-accumulated gradient to carry over).
                if time.perf_counter() - t_start > BUDGET and i + 1 < len(order):
                    state.update(epoch=epoch, i=i + 1)
                    ckpt.mkdir(parents=True, exist_ok=True)
                    torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
                                "rng": rng.getstate(), "torch_rng": torch.get_rng_state(),
                                "cuda_rng": torch.cuda.get_rng_state(), "state": state,
                                "minutes": before + (time.perf_counter() - t_start) / 60}, ckpt / "state.pt")
                    print(f"checkpoint at epoch {epoch}, group {i + 1} of {len(order)}; run again", flush=True)
                    sys.exit(3)
        print(f"epoch {epoch}: mean loss {state['total'] / len(order):.3f}", flush=True)
        state["order"] = None
    model.eval()
    return tok, model


def main(teacher):
    rng = random.Random(tune.SEED)
    docs = {k: v["doc"] for k, v in json.loads((HERE / "derived" / "tools.json").read_text(encoding="utf-8")).items()}
    rows = {r["id"]: r for r in map(json.loads, (HERE / "train2.jsonl").read_text(encoding="utf-8").splitlines())}
    labs = labels(teacher, rows)
    fit, held = [], []
    for i, r in rows.items():
        if i not in labs:
            continue
        pos, skip = labs[i]
        row = {"query": r["query"], "gold": [pos], "teacher": pos, "gen_gold": r["gen_gold"],
               "candidates": [c for c in r["candidates"] if c not in skip or c == pos],
               "ranked_all": [c for c in r["ranked_all"] if c not in skip or c == pos]}
        (fit if r["split"] == "fit" else held).append(row)
    ckpt = HERE / "models" / f"ckpt-{teacher}"
    prior = torch.load(ckpt / "state.pt", weights_only=False)["minutes"] if (ckpt / "state.pt").exists() else 0.0
    t0 = time.perf_counter()
    tok, model = train(tune.groups_t(fit, docs, rng), rng, ckpt)
    minutes = prior + (time.perf_counter() - t0) / 60
    out = HERE / "models" / f"gte-{teacher}"
    model.save_pretrained(out); tok.save_pretrained(out)
    score, names = tune.scorer(tok, model), list(docs)
    agree = gold = 0
    for r in held:
        s = score(r["query"], [docs[n] for n in names])
        best = names[max(range(len(s)), key=s.__getitem__)]
        agree += best == r["teacher"]
        gold += best in r["gen_gold"]
    res = {"teacher": teacher, "fit": len(fit), "held": len(held), "held_agree_teacher": agree,
           "held_match_gen_gold": gold, "teacher_match_gen_gold": sum(r["teacher"] in r["gen_gold"] for r in held),
           "train_minutes": round(minutes, 1)}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"train_{teacher}.json").write_text(json.dumps(res), encoding="utf-8")
    if (ckpt / "state.pt").exists():
        (ckpt / "state.pt").unlink()
        ckpt.rmdir()
    print(res, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
