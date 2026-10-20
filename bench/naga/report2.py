"""Round 2 tables, appended to RESULTS.md between the r2 markers (round 1's tables are left as they are).
Reads results/ (round 1) and results2/ (round 2, incl. retry.* and phase4.* files). Plain python."""
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
R1, R2 = HERE / "results", HERE / "results2"
START, END = "<!-- r2:start -->", "<!-- r2:end -->"
ORDER = ["baseline", "harrier-bi", "gte-rerank", "qwen3-rerank", "nli", "gliner2", "laya", "von", "gemma4", "tuned"]


def load(d, engine, task):
    p = d / f"{engine}.{task}.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else None


def hit(r, k):
    return any(x in r["gold"] for x in r["ranking"][:k])


def n(rows, k, split=None):
    sel = [r for r in rows if split is None or r["split"] == split]
    return f"{sum(hit(r, k) for r in sel)}/{len(sel)}"


def ms(rows):
    return f"{statistics.median(r['latency_s'] for r in rows) * 1000:.0f}"


def main_tables():
    out = []
    for task, title in (("T", "T, mode top10 (find_tool's 10 candidates)"), ("Tall", "T, mode all (all 90 tools)")):
        out.append(f"#### {title}\n\n| engine | TRAIN top-1 | TRAIN top-3 | TEST top-1 | TEST top-3 | median ms | note |\n|---|---|---|---|---|---|---|")
        for e in ORDER:
            r = load(R2, e, task)
            if r:
                note = ""
                if task == "Tall" and e in ("laya", "gemma4"):
                    note = "harrier top 20 as options"
                if r and any("error" in x for x in r):
                    note += f" {sum('error' in x for x in r)} errors"
                out.append(f"| {e} | {n(r,1,'TRAIN')} | {n(r,3,'TRAIN')} | {n(r,1,'TEST')} | {n(r,3,'TEST')} | {ms(r)} | {note.strip()} |")
        out.append("")
    for task in ("blocks", "distributions"):
        out.append(f"#### B: {task}\n\n| engine | R1 acc | R1 top-3 | R2 acc | R2 top-3 | R2 median ms | note |\n|---|---|---|---|---|---|---|")
        for e in ORDER:
            r2 = load(R2, e, task)
            if r2:
                r1 = load(R1, e, task)
                note = ("shortlist: harrier top 20" if e in ("laya", "gemma4") else "all labels" if e == "von" else "")
                out.append(f"| {e} | {n(r1,1) if r1 else '-'} | {n(r1,3) if r1 else '-'} | {n(r2,1)} | {n(r2,3)} | {ms(r2)} | {note} |")
        out.append("")
    return "\n".join(out)


def retry_tables():
    out = ["| engine | task | variant | TEST 1 / 2 / 3 | TRAIN 1 / 2 / 3 | mean ms per request (TEST) |\n|---|---|---|---|---|---|"]
    oracle = ["| engine | task | oracle TEST top-1 / 2 / 3 | oracle TRAIN top-1 / 2 / 3 |\n|---|---|---|---|"]
    for e in ("tuned", "laya"):
        for task in ("T", "Tall", "blocks", "distributions"):
            base = load(R2, e, task)
            if base:
                te = [r for r in base if r["split"] == "TEST"]
                tr = [r for r in base if r["split"] == "TRAIN"]
                f = lambda rows: " / ".join(str(sum(hit(r, k) for r in rows)) for k in (1, 2, 3)) + f" of {len(rows)}" if rows else "-"
                oracle.append(f"| {e} | {task} | {f(te)} | {f(tr)} |")
            for v in ("plain", "nudged"):
                rows = load(R2, f"retry.{e}.{v}", task)
                if not rows:
                    continue
                te = [r for r in rows if r["split"] == "TEST"]
                tr = [r for r in rows if r["split"] == "TRAIN"]
                g = lambda sel: " / ".join(str(sum(r["won_at"] is not None and r["won_at"] <= k for r in sel)) for k in (1, 2, 3)) + f" of {len(sel)}" if sel else "-"
                out.append(f"| {e} | {task} | {v} | {g(te)} | {g(tr)} | {statistics.mean(r['time_s'] for r in te) * 1000:.0f} |")
    return "\n".join(out) + "\n\nOracle (the ranking of the round-2 run, no retry):\n\n" + "\n".join(oracle)


def main():
    text = (HERE / "RESULTS.md").read_text(encoding="utf-8")
    body = ("## Round 2 (2026-10-20)\n\nFuller block and distribution descriptions (ArenaPy-desc, post-desc 4664d7e9), T also over all 90 tools. "
            "Fields not rerun (their texts did not change).\n\n" + main_tables() +
            "\n## Round 2, retries\n\n" + retry_tables() + "\n")
    p4 = HERE / "phase4.md"
    if p4.exists():
        body += "\n## Phase 4\n\n" + p4.read_text(encoding="utf-8")
    block = f"{START}\n{body}{END}"
    if START in text:
        text = text.split(START)[0] + block + text.split(END, 1)[1]
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    (HERE / "RESULTS.md").write_text(text, encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
