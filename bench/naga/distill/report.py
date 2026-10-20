"""Tables for the distillation section of RESULTS.md: `python distill/report.py` (stdlib).

Benchmark: TEST2 (100) and HELD_OUT_2 (25), mode top10 (find_tool's 10 candidates, task T) and all 90 (Tall).
Plain retry for the students: a cross-encoder scores each option on its own, so removing a rejected option
leaves the rest in the same order and try k is right exactly when the gold is in the first k (time = the
measured decision time times the tries used, an estimate). Labels: how often each teacher agrees with the
generated gold and with the other teacher, and what labelling cost."""
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
ENGINES = [("baseline", "find_tool alone"), ("gte-rerank", "gte, untuned"), ("gte-gemma4", "gte <- Gemma labels"),
           ("gte-haiku", "gte <- Haiku labels"), ("gemma4", "Gemma 4 E4B"), ("haiku", "Claude Haiku 5.5 (API)")]
SPLITS = ("TEST2", "HELD_OUT_2")


def rows(name):
    p = RES / f"{name}.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else None


def hit(r, k):
    return any(g in r["ranking"][:k] for g in r["gold"])


def bench():
    print("| engine | mode | TEST2 top-1 | TEST2 top-3 | HELD_OUT_2 top-1 | HELD_OUT_2 top-3 | median ms | errors |")
    print("|---|---|---|---|---|---|---|---|")
    for mode, task in (("all 90", "Tall"), ("top10", "T")):
        for e, label in ENGINES:
            rs = rows(f"{e}.{task}")
            if rs is None:
                print(f"| {label} | {mode} | not run | | | | | |")
                continue
            cells = []
            for s in SPLITS:
                sel = [r for r in rs if r["split"] == s]
                cells += [f"{sum(hit(r, 1) for r in sel)}/{len(sel)}", f"{sum(hit(r, 3) for r in sel)}/{len(sel)}"]
            med = statistics.median(r["latency_s"] for r in rs) * 1000
            err = sum("error" in r for r in rs)
            print(f"| {label} | {mode} | {' | '.join(cells)} | {med:.0f} | {err or ''} |")
    print("\nPlain retry, students (right within 1 / 2 / 3 tries; mean ms per request, retries included):\n")
    print("| student | mode | TEST2 1 / 2 / 3 | HELD_OUT_2 1 / 2 / 3 | mean ms (TEST2) |")
    print("|---|---|---|---|---|")
    for mode, task in (("all 90", "Tall"), ("top10", "T")):
        for e in ("gte-gemma4", "gte-haiku"):
            rs = rows(f"{e}.{task}")
            if not rs:
                continue
            cells = []
            for s in SPLITS:
                sel = [r for r in rs if r["split"] == s]
                cells.append(" / ".join(str(sum(hit(r, k) for r in sel)) for k in (1, 2, 3)) + f" of {len(sel)}")
            t2 = [r for r in rs if r["split"] == "TEST2"]
            tries = [next((k for k in (1, 2, 3) if hit(r, k)), 3) for r in t2]
            ms = statistics.mean(r["latency_s"] * k for r, k in zip(t2, tries)) * 1000
            print(f"| {e} | {mode} | {' | '.join(cells)} | {ms:.0f} |")


def labels():
    train = {r["id"]: r for r in map(json.loads, (HERE / "train2.jsonl").read_text(encoding="utf-8").splitlines())}
    lab = {t: {r["id"]: r for r in map(json.loads, (HERE / "labels" / f"{t}.jsonl").read_text(encoding="utf-8").splitlines())}
           for t in ("gemma4", "haiku") if (HERE / "labels" / f"{t}.jsonl").exists()}
    print("\n| teacher | labelled | top-1 = generated gold | generated gold in top 3 | labelling time | API tokens in / out |")
    print("|---|---|---|---|---|---|")
    for t, ls in lab.items():
        top1 = sum(r["ranking"][:1] and r["ranking"][0] in train[i]["gen_gold"] for i, r in ls.items())
        top3 = sum(any(g in r["ranking"][:3] for g in train[i]["gen_gold"]) for i, r in ls.items())
        mins = sum(r["latency_s"] for r in ls.values()) / 60
        tok = (f"{sum(r.get('tokens_in', 0) for r in ls.values()):,} / {sum(r.get('tokens_out', 0) for r in ls.values()):,}"
               if t == "haiku" else "-")
        print(f"| {t} | {len(ls)}/{len(train)} | {top1} | {top3} | {mins:.0f} min | {tok} |")
    if len(lab) == 2:
        both = set(lab["gemma4"]) & set(lab["haiku"])
        same = sum(lab["gemma4"][i]["ranking"][:1] == lab["haiku"][i]["ranking"][:1] for i in both)
        print(f"\nThe two teachers give the same top-1 on {same} of {len(both)} requests.")
    for t in ("gemma4", "haiku"):
        p = RES / f"train_{t}.json"
        if p.exists():
            r = json.loads(p.read_text(encoding="utf-8"))
            print(f"- student gte <- {t}: trained on {r['fit']} requests in {r['train_minutes']} min (GPU); held-out "
                  f"{r['held']}: agrees with its teacher on {r['held_agree_teacher']}, matches the generated gold on "
                  f"{r['held_match_gen_gold']} (the teacher itself: {r['teacher_match_gen_gold']}).")


if __name__ == "__main__":
    bench()
    labels()
