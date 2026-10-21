"""Tables for RESULTS.md "Round 5: queries as the agent writes them": `python distill/report5.py` (stdlib).

AGENT3 (274 find_tool queries Opus 5.5 wrote as the naga agent), modes all 90 (Tall) and top10 (T), results in
distill/results4: overall, per seed source and per seed writer; the paired Haiku vs gte-opus count on all 90 (rows
one gets right first time and the other does not, with an exact two-sided sign test); Opus cost at list price."""
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results4"
ENGINES = [("baseline", "find_tool alone"), ("gte-rerank", "gte, untuned"), ("gte-haiku", "gte <- Haiku labels"),
           ("gte-opus", "gte <- Opus labels"), ("gte-agreed", "gte <- agreed labels"),
           ("haiku", "Claude Haiku 5.5 (API)"), ("opus", "Claude Opus 5.5 (API)")]
MODES = (("all 90", "Tall"), ("top10", "T"))
PRICE = {"in": 4.0, "write": 5.0, "read": 0.20, "out": 20.0}


def rows(name):
    p = RES / f"{name}.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def hit(r, k):
    return any(g in r["ranking"][:k] for g in r["gold"])


META = {f"AGENT3-{i}": r for i, r in enumerate(json.loads((HERE / "derived4" / "tool_queries.json").read_text(encoding="utf-8"))["AGENT3"])}
SOURCES = ["TEST3", "TEST2", "HELD_OUT_2"]
WRITERS = ["Claude Opus 5.5", "Gemma 4 E4B", "Qwen3-1.7B", "LiquidAI d1-3B", "Claude Sonnet 5.5", "round-2 set"]


def overall():
    print("| engine | mode | top-1 | top-3 | median ms |")
    print("|---|---|---|---|---|")
    for mode, task in MODES:
        for e, label in ENGINES:
            rs = rows(f"{e}.{task}")
            med = statistics.median(r["latency_s"] for r in rs) * 1000
            print(f"| {label} | {mode} | {sum(hit(r, 1) for r in rs)}/{len(rs)} | {sum(hit(r, 3) for r in rs)}/{len(rs)} | {med:.0f} |")


def split(key, values, title):
    n = {v: sum(m[key] == v for m in META.values()) for v in values}
    for mode, task in MODES:
        print(f"\nTop-1 by seed {title}, {mode}:\n")
        print("| engine | " + " | ".join(f"{v} ({n[v]})" for v in values) + " |")
        print("|---|" + "---|" * len(values))
        for e, label in ENGINES:
            rs = rows(f"{e}.{task}")
            print(f"| {label} | " + " | ".join(str(sum(hit(r, 1) for r in rs if META[r["id"]][key] == v)) for v in values) + " |")


def paired(a="haiku", b="gte-opus", task="Tall"):
    ra, rb = {r["id"]: hit(r, 1) for r in rows(f"{a}.{task}")}, {r["id"]: hit(r, 1) for r in rows(f"{b}.{task}")}
    only_a = sum(ra[i] and not rb[i] for i in ra)
    only_b = sum(rb[i] and not ra[i] for i in ra)
    n, k = only_a + only_b, min(only_a, only_b)
    p = min(1.0, 2 * sum(math.comb(n, j) for j in range(k + 1)) / 2 ** n) if n else 1.0
    mode = {t: m for m, t in MODES}[task]
    print(f"\nPaired, {mode}: {a} right and {b} wrong on {only_a} rows, the reverse on {only_b}; sign test p = {p:.2f}.")


def cost(rs):
    tin = sum(r.get("tokens_in", 0) for r in rs)
    rd, wr = sum(r.get("cache_read", 0) for r in rs), sum(r.get("cache_write", 0) for r in rs)
    out = sum(r.get("tokens_out", 0) for r in rs)
    return tin, out, ((tin - rd - wr) * PRICE["in"] + wr * PRICE["write"] + rd * PRICE["read"] + out * PRICE["out"]) / 1e6


def opus_cost():
    print("\n| Opus 5.5 use | calls | tokens in | tokens out | cost USD |")
    print("|---|---|---|---|---|")
    total = 0.0
    for name, rs in (("writing AGENT3 queries", [json.loads(x) for x in (HERE / "agent3_raw.jsonl").read_text(encoding="utf-8").splitlines()]),
                     ("picker, all 90", rows("opus.Tall")), ("picker, top10", rows("opus.T"))):
        tin, out, usd = cost(rs)
        total += usd
        print(f"| {name} | {len(rs)} | {tin:,} | {out:,} | {usd:.2f} |")
    print(f"| total | | | | {total:.2f} |")


if __name__ == "__main__":
    overall()
    split("source", SOURCES, "source")
    split("writer", WRITERS, "writer")
    paired()
    paired("haiku", "gte-opus", "T")
    opus_cost()
