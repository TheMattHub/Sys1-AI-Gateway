"""Tables for RESULTS.md "Round 4: a multi-writer test": `python distill/report4.py` (stdlib).

TEST3 (150, four writers), TEST2 (100) and HELD_OUT_2 (25), modes all 90 (Tall) and top10 (T), results in
distill/results3. Median ms is over the TEST3 rows only (the TEST2 rows of the earlier engines were measured
last night). Per-writer top-1 on TEST3. Opus cost at the list price of claude-opus-5-5 ($4 / M input, $5 / M
cache write, $0.20 / M cache read, $20 / M output)."""
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results3"
ENGINES = [("baseline", "find_tool alone"), ("gte-rerank", "gte, untuned"), ("gte-gemma4", "gte <- Gemma labels"),
           ("gte-haiku", "gte <- Haiku labels"), ("gte-opus", "gte <- Opus labels (new)"),
           ("gte-agreed", "gte <- agreed labels (new)"), ("gemma4", "Gemma 4 E4B"), ("d1-3b", "d1-3B"),
           ("haiku", "Claude Haiku 5.5 (API)"), ("opus", "Claude Opus 5.5 (API, new)")]
WRITERS = ["Claude Opus 5.5", "Gemma 4 E4B", "Qwen3-1.7B", "LiquidAI d1-3B"]
PRICE = {"in": 4.0, "write": 5.0, "read": 0.20, "out": 20.0}
MODES = (("all 90", "Tall"), ("top10", "T"))


def rows(name):
    p = RES / f"{name}.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else None


def hit(r, k):
    return any(g in r["ranking"][:k] for g in r["gold"])


def writer_of():
    q = json.loads((HERE / "derived3" / "tool_queries.json").read_text(encoding="utf-8"))["TEST3"]
    return {f"TEST3-{i}": r["writer"] for i, r in enumerate(q)}


def cell(sel, k):
    return f"{sum(hit(r, k) for r in sel)}/{len(sel)}" if sel else "-"


def bench():
    print("| engine | mode | TEST3 top-1 | TEST3 top-3 | median ms | TEST2 top-1 | TEST2 top-3 | HELD_OUT_2 top-1 | errors |")
    print("|---|---|---|---|---|---|---|---|---|")
    for mode, task in MODES:
        for e, label in ENGINES:
            rs = rows(f"{e}.{task}")
            if rs is None:
                print(f"| {label} | {mode} | not run | | | | | | |")
                continue
            by = {s: [r for r in rs if r["split"] == s] for s in ("TEST3", "TEST2", "HELD_OUT_2")}
            med = statistics.median(r["latency_s"] for r in by["TEST3"]) * 1000
            err = sum("error" in r for r in by["TEST3"])
            print(f"| {label} | {mode} | {cell(by['TEST3'], 1)} | {cell(by['TEST3'], 3)} | {med:.0f} | "
                  f"{cell(by['TEST2'], 1)} | {cell(by['TEST2'], 3)} | {cell(by['HELD_OUT_2'], 1)} | {err or ''} |")


def per_writer():
    w = writer_of()
    n = {x: sum(v == x for v in w.values()) for x in WRITERS}
    for mode, task in MODES:
        print(f"\nTEST3 top-1 per writer, {mode}:\n")
        print("| engine | " + " | ".join(f"{x} ({n[x]})" for x in WRITERS) + " | all (150) |")
        print("|---|" + "---|" * (len(WRITERS) + 1))
        for e, label in ENGINES:
            rs = rows(f"{e}.{task}")
            if rs is None:
                continue
            t3 = [r for r in rs if r["split"] == "TEST3"]
            cells = [str(sum(hit(r, 1) for r in t3 if w[r["id"]] == x)) for x in WRITERS]
            print(f"| {label} | {' | '.join(cells)} | {sum(hit(r, 1) for r in t3)} |")


def cost(rs):
    tin = sum(r.get("tokens_in", 0) for r in rs)
    rd, wr = sum(r.get("cache_read", 0) for r in rs), sum(r.get("cache_write", 0) for r in rs)
    out = sum(r.get("tokens_out", 0) for r in rs)
    usd = ((tin - rd - wr) * PRICE["in"] + wr * PRICE["write"] + rd * PRICE["read"] + out * PRICE["out"]) / 1e6
    return tin, rd, out, usd


def opus_cost():
    print("\n| Opus 5.5 use | calls | tokens in (of which cache reads) | tokens out | cost USD |")
    print("|---|---|---|---|---|")
    parts = [("writing TEST3 rows", [json.loads(x) for x in (HERE / "test3_raw" / "opus.jsonl").read_text(encoding="utf-8").splitlines()]),
             ("benchmark, all 90 (TEST3+TEST2+HELD_OUT_2)", rows("opus.Tall") or []),
             ("benchmark, top10", rows("opus.T") or []),
             ("labels, TRAIN2", [json.loads(x) for x in (HERE / "labels" / "opus.jsonl").read_text(encoding="utf-8").splitlines()])]
    total = 0.0
    tin_b, rd_b, _, _ = cost(parts[1][1])
    for name, rs in parts:
        tin, rd, out, usd = cost(rs)
        if name.startswith("labels") and not rd:
            # label.py did not keep the cache fields on this run; the same cached system block over the same 90
            # tools was read from cache on rd_b / tin_b of the benchmark's all-90 input, so that share is assumed.
            rd = round(tin * rd_b / tin_b)
            usd = ((tin - rd) * PRICE["in"] + rd * PRICE["read"] + out * PRICE["out"]) / 1e6
            name += " (cache share assumed as in the all-90 benchmark)"
        total += usd
        print(f"| {name} | {len(rs)} | {tin:,} ({rd:,}) | {out:,} | {usd:.2f} |")
    print(f"| total | | | | {total:.2f} |")


def labels():
    train = {r["id"]: r for r in map(json.loads, (HERE / "train2.jsonl").read_text(encoding="utf-8").splitlines())}
    lab = {t: {r["id"]: r["ranking"] for r in map(json.loads, (HERE / "labels" / f"{t}.jsonl").read_text(encoding="utf-8").splitlines())}
           for t in ("gemma4", "haiku", "opus")}
    print("\n| teacher | top-1 = generated gold (of 1,067) | generated gold in top 3 |")
    print("|---|---|---|")
    for t, ls in lab.items():
        print(f"| {t} | {sum(bool(v) and v[0] in train[i]['gen_gold'] for i, v in ls.items())} | "
              f"{sum(any(g in v[:3] for g in train[i]['gen_gold']) for i, v in ls.items())} |")
    same = sum(lab["haiku"][i][:1] == lab["opus"][i][:1] for i in train)
    print(f"\nHaiku and Opus give the same top-1 on {same} of {len(train)} TRAIN2 requests.")
    for t in ("opus", "agreed"):
        p = HERE / "results" / f"train_{t}.json"
        if p.exists():
            r = json.loads(p.read_text(encoding="utf-8"))
            print(f"- student gte <- {t}: trained on {r['fit']} requests in {r['train_minutes']} min (GPU); held-out "
                  f"{r['held']}: agrees with its label on {r['held_agree_teacher']}, matches the generated gold on "
                  f"{r['held_match_gen_gold']} (the label itself: {r['teacher_match_gen_gold']}).")


if __name__ == "__main__":
    bench()
    per_writer()
    opus_cost()
    labels()
