"""Build the tables in RESULTS.md from results/*.jsonl (rewrites only the part between the markers).

Threshold: the lowest confidence t at which TRAIN (T's EVAL + HELD_OUT) top-1 accuracy over the rows with
confidence >= t is at least 90% on at least 5 rows. B has no TRAIN rows, so B uses the same engine's T
threshold (its scale differs by option count: read B's coverage column as indicative only)."""
import json
import statistics

import common

START, END = "<!-- tables:start -->", "<!-- tables:end -->"
ORDER = ["baseline", "harrier-bi", "gte-rerank", "qwen3-rerank", "nli", "gliner2", "laya", "von", "gemma4",
         "tuned"]


def load():
    out = {}
    for p in sorted(common.RESULTS.glob("*.jsonl")):
        engine, task = p.stem.rsplit(".", 1)
        out[(engine, task)] = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return out


def hit(r, k):
    return any(x in r["gold"] for x in r["ranking"][:k])


def threshold(rows):
    rows = sorted((r for r in rows if "error" not in r), key=lambda r: -r["confidence"])
    best = None
    for i in range(5, len(rows) + 1):
        acc = sum(hit(r, 1) for r in rows[:i]) / i
        if acc >= 0.9 and (i == len(rows) or rows[i]["confidence"] < rows[i - 1]["confidence"]):
            best = rows[i - 1]["confidence"]
    return best


def above(rows, t):
    if t is None:
        return "-"
    sel = [r for r in rows if r["confidence"] >= t and "error" not in r]
    if not sel:
        return f"0/{len(rows)}"
    return f"{len(sel)}/{len(rows)} at {sum(hit(r, 1) for r in sel) / len(sel):.0%}"


def ms(rows):
    return f"{statistics.median(r['latency_s'] for r in rows) * 1000:.0f}"


def errs(rows):
    n = sum("error" in r for r in rows)
    return str(n) if n else ""


def engines(data, task):
    seen = [e for e, t in data if t == task]
    return sorted(set(seen), key=lambda e: (ORDER.index(e) if e in ORDER else 99, e))


def tables(data):
    out = []
    base = data.get(("baseline", "T"))
    if base:
        cand = json.loads((common.DERIVED / "tool_queries.json").read_text(encoding="utf-8"))
        rec = {s: sum(any(g in r["candidates"] for g in r["gold"]) for r in rows) for s, rows in cand.items()}
        out.append(f"### T: tool choice (re-rank of find_tool's top 10)\n\nCandidate recall@10 (the ceiling): "
                   f"TRAIN {rec['TRAIN']}/{len(cand['TRAIN'])}, TEST {rec['TEST']}/{len(cand['TEST'])}.\n")
        out.append("| engine | TRAIN top-1 | TRAIN top-3 | TEST top-1 | TEST top-3 | median ms | threshold (TRAIN) "
                   "| TEST above threshold | errors |\n|---|---|---|---|---|---|---|---|---|")
        for e in engines(data, "T"):
            rows = data[(e, "T")]
            tr = [r for r in rows if r["split"] == "TRAIN"]
            te = [r for r in rows if r["split"] == "TEST"]
            t = threshold(tr)
            out.append(f"| {e} | {sum(hit(r, 1) for r in tr)}/{len(tr)} | {sum(hit(r, 3) for r in tr)}/{len(tr)} | "
                       f"{sum(hit(r, 1) for r in te)}/{len(te)} | {sum(hit(r, 3) for r in te)}/{len(te)} | {ms(rows)} | "
                       f"{'-' if t is None else f'{t:.3f}'} | {above(te, t)} | {errs(rows)} |")
        out.append("")
    for task in ("blocks", "distributions", "fields"):
        es = engines(data, task)
        if not es:
            continue
        n = len(data[(es[0], task)])
        out.append(f"### B: {task} ({n} rows, all TEST)\n")
        out.append("| engine | accuracy | top-3 | median ms | above T threshold | errors |\n|---|---|---|---|---|---|")
        for e in es:
            rows = data[(e, task)]
            t = threshold([r for r in data.get((e, "T"), []) if r["split"] == "TRAIN"])
            out.append(f"| {e} | {sum(hit(r, 1) for r in rows)}/{len(rows)} | {sum(hit(r, 3) for r in rows)}/{len(rows)} "
                       f"| {ms(rows)} | {above(rows, t)} | {errs(rows)} |")
        out.append("")
    return "\n".join(out)


def main():
    path = common.HERE / "RESULTS.md"
    text = path.read_text(encoding="utf-8") if path.exists() else f"# Results\n\n{START}\n{END}\n"
    head, rest = text.split(START, 1)
    tail = rest.split(END, 1)[1]
    path.write_text(f"{head}{START}\n{tables(load())}\n{END}{tail}", encoding="utf-8")
    print(tables(load()))


if __name__ == "__main__":
    main()
