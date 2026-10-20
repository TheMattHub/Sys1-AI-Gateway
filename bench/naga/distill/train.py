"""Train one gte student per teacher on TRAIN2 (bench venv): `python distill/train.py gemma4|haiku`.

tune.py's recipe as it is (cross-encoder, listwise loss, find_tool's top 10 and ranks 11-90 as hard negatives,
2 epochs, lr 2e-5, seed 0). Positive = the teacher's top-1; its 2nd and 3rd picks are left out of the
negatives (tune.py's loss takes one positive, so no soft positives). Fits on the 90% "fit" split, one run;
then the 10% "held" split is scored over all 90 tools: agreement with the teacher's top-1 and with the
generated gold. Saves distill/models/gte-<teacher> (not committed) and distill/results/train_<teacher>.json."""
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import tune  # noqa: E402


def main(teacher):
    rng = random.Random(tune.SEED)
    docs = {k: v["doc"] for k, v in json.loads((HERE / "derived" / "tools.json").read_text(encoding="utf-8")).items()}
    rows = {r["id"]: r for r in map(json.loads, (HERE / "train2.jsonl").read_text(encoding="utf-8").splitlines())}
    labels = {r["id"]: r["ranking"] for r in map(json.loads, (HERE / "labels" / f"{teacher}.jsonl").read_text(encoding="utf-8").splitlines())}
    fit, held = [], []
    for i, r in rows.items():
        lab = labels.get(i)
        if not lab:
            continue
        top3 = set(lab[:3])
        row = {"query": r["query"], "gold": [lab[0]], "teacher": lab[0], "gen_gold": r["gen_gold"],
               "candidates": [c for c in r["candidates"] if c not in top3 or c == lab[0]],
               "ranked_all": [c for c in r["ranked_all"] if c not in top3 or c == lab[0]]}
        (fit if r["split"] == "fit" else held).append(row)
    t0 = time.perf_counter()
    tok, model = tune.train(tune.groups_t(fit, docs, rng), rng)
    minutes = (time.perf_counter() - t0) / 60
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
    print(res, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
