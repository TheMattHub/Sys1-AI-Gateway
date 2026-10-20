"""The round-3 table of RESULTS.md: `python report3.py` (stdlib).

Every engine on TEST2 (100, distill/results, T = find_tool's top 10, Tall = all 90 tools) and on round 2's blocks
(40) and distributions (30) (results2/). "-" = not run (see RESULTS.md, Round 3, for why)."""
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINES = [  # result name, label, kind
    ("baseline", "find_tool alone", "-"), ("harrier-bi", "harrier (bi-encoder)", "encoder"),
    ("gte-rerank", "gte-reranker, zero-shot", "encoder"), ("tuned-r1", "gte-reranker, round-1 fine-tune", "encoder"),
    ("gte-haiku", "gte <- Haiku labels", "encoder"), ("gte-gemma4", "gte <- Gemma labels", "encoder"),
    ("qwen3-rerank", "Qwen3-Reranker-0.6B", "encoder"), ("nli", "ModernBERT-NLI", "encoder"),
    ("gliner2", "GLiNER2.5", "System-1"), ("laya", "Laya", "System-1"), ("von", "Von 1.3", "System-1"),
    ("d1-omni", "d1-omni-600M (new)", "System-1"), ("d1-3b", "d1-3B (new)", "System-1"),
    ("openthai", "OpenThai-SystemOne (new)", "System-1"), ("openthai-ollama", "OpenThai, Ollama build (new)", "System-1"),
    ("anyjev", "AnyJev L0 on Qwen3-1.7B (new)", "System-1"),
    ("gemma4", "Gemma 4 E4B", "LLM"), ("haiku", "Claude Haiku 5.5 (API)", "LLM")]


def rows(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else None


def cell(rs, split=None):
    if rs is None:
        return "-", "-"
    sel = [r for r in rs if split is None or r["split"] == split]
    hit = lambda r, k: any(g in r["ranking"][:k] for g in r["gold"])
    return f"{sum(hit(r, 1) for r in sel)} / {sum(hit(r, 3) for r in sel)}", f"{statistics.median(r['latency_s'] for r in rs) * 1000:.0f}"


def main():
    print("| engine | kind | TEST2 top10: top-1 / top-3 | ms | TEST2 all 90: top-1 / top-3 | ms | HELD_OUT_2 all 90 | "
          "blocks (40) | distributions (30) | B ms |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for e, label, kind in ENGINES:
        t, tall = rows(HERE / "distill" / "results" / f"{e}.T.jsonl"), rows(HERE / "distill" / "results" / f"{e}.Tall.jsonl")
        b, d = rows(HERE / "results2" / f"{e}.blocks.jsonl"), rows(HERE / "results2" / f"{e}.distributions.jsonl")
        (t1, tms), (a1, ams), (h1, _) = cell(t, "TEST2"), cell(tall, "TEST2"), cell(tall, "HELD_OUT_2")
        (b1, bms), (d1, _) = cell(b), cell(d)
        print(f"| {label} | {kind} | {t1} | {tms} | {a1} | {ams} | {h1} | {b1} | {d1} | {bms} |")


if __name__ == "__main__":
    main()
