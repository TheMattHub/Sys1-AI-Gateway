"""Charts for the README and the study report, built from results2/ (round 2). Needs matplotlib.

    python bench/naga/plot.py        # writes docs/screenshots/*.png

hero.png: accuracy vs median latency per engine (tool choice, model building).
retries.png: TEST rows right within 1-3 tries, plain vs nudged retry.
phase4.png: tool choice TEST top-1 over all 90 tools, with fewer choices.
"""
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import patheffects  # noqa: E402

HERE = Path(__file__).resolve().parent
R2 = HERE / "results2"
OUT = HERE.parents[1] / "docs" / "screenshots"
COLORS = {"harrier-bi": "#8c8c8c", "gte-rerank": "#1f77b4", "qwen3-rerank": "#2ca02c", "nli": "#9467bd", "gliner2": "#8c564b",
          "laya": "#ff7f0e", "von": "#e377c2", "gemma4": "#d62728", "tuned": "#17becf", "haiku": "#000000",
          "gte-gemma4": "#17becf", "gte-haiku": "#17becf", "gte-opus": "#17becf", "gte-agreed": "#17becf",
          "d1-omni": "#eb6834", "d1-3b": "#eb6834", "openthai": "#eb6834", "anyjev": "#eb6834"}
LABELS = {"gte-rerank": "gte-reranker (zero-shot)", "qwen3-rerank": "Qwen3-Reranker-0.6B", "gemma4": "Gemma 4 E4B", "laya": "Laya",
          "tuned": "gte-reranker (fine-tuned)", "harrier-bi": "harrier (bi-encoder)", "nli": "ModernBERT-NLI", "gliner2": "GLiNER2.5",
          "von": "Von 1.3", "haiku": "Claude Haiku 5.5 (API)",
          "gte-gemma4": "gte <- Gemma labels", "gte-haiku": "gte <- Haiku labels",
          "gte-opus": "gte <- Opus labels", "gte-agreed": "gte <- agreed labels",
          "d1-omni": "d1-omni-600M", "d1-3b": "d1-3B (Q8_0)", "openthai": "OpenThai-SystemOne", "anyjev": "AnyJev on Qwen3-1.7B"}


# What kind of model each engine is, drawn as the point's shape: System-1 decision models (built to
# answer a multiple-choice question in one pass), encoders (rerankers, NLI, embeddings) and LLMs.
KINDS = {"System-1 decision model": ("o", ("laya", "von", "gliner2", "d1-omni", "d1-3b", "openthai", "anyjev")),
         "encoder (reranker, NLI, embedding)": ("s", ("gte-rerank", "tuned", "qwen3-rerank", "nli", "harrier-bi",
                                                            "gte-gemma4", "gte-haiku", "gte-opus", "gte-agreed")),
         "LLM": ("^", ("gemma4", "haiku"))}
MARKER = {e: m for m, es in KINDS.values() for e in es}
KIND = {e: k for k, (_, es) in KINDS.items() for e in es}
# Colour follows the kind too (three hues, validated with the dataviz skill's palette checks, light and
# dark): eleven engine hues could not be told apart, and every point carries its name anyway.
KIND_COLOR = {"System-1 decision model": "#eb6834", "encoder (reranker, NLI, embedding)": "#2a78d6", "LLM": "#1baf7a"}


def frontier(pts):
    """The engines no other engine beats on both speed and accuracy, fastest first: walk by latency and
    keep each one more accurate than every faster one."""
    out, best = [], float("-inf")
    for e, (x, y) in sorted(pts.items(), key=lambda kv: (kv[1][0], -kv[1][1])):
        if y > best:
            out.append(e)
            best = y
    return out

# Label offsets (points) where two engines sit almost on top of each other.
# Shared with the interactive chart through engines.json (dx, dy in points/pixels, y up).
OFFSET = {"tools": {"laya": (10, -3), "qwen3-rerank": (8, -14), "gte-rerank": (24, -3), "gte-haiku": (8, -16), "gte-gemma4": (8, -14), "gte-opus": (8, 4), "gte-agreed": (8, 2),
                    "d1-3b": (-78, -15), "d1-omni": (-24, 9), "openthai": (6, -14)},
          "building": {"gliner2": (8, -14), "laya": (10, -3), "d1-3b": (-82, 6), "openthai": (-40, 9)}}


# The distilled students (distill/train.py) have tool-choice results only, in distill/results/; their
# HELD_OUT_2 rows are round 2's 25 TEST questions, so they join the tool-choice panel on the same rows.
STUDENTS = ("gte-gemma4", "gte-haiku")
# Round 4's students (gte <- Opus, gte <- agreed labels) were benchmarked under BENCH_ROUND=test3 (distill/results3),
# which holds the same 25 HELD_OUT_2 rows.
STUDENTS4 = ("gte-opus", "gte-agreed")
# Round 3's engines ran tool choice on TEST2 only (distill/results) and model building in results2/; their
# HELD_OUT_2 rows are the same 25 questions, so they join the tool-choice panel like the students.
ROUND3 = ("d1-omni", "d1-3b", "openthai", "anyjev")


def load(name):
    e, _, task = name.partition(".")
    student = e in STUDENTS + STUDENTS4 or (e in ROUND3 and task in ("T", "Tall"))
    p = (HERE / "distill" / ("results3" if e in STUDENTS4 else "results") if student else R2) / f"{name}.jsonl"
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else None
    if rows and student:
        rows = [{**r, "split": "TEST"} for r in rows if r["split"] == "HELD_OUT_2"]
    return rows


def top1(rows, split=None):
    sel = [r for r in rows if split is None or r["split"] == split]
    return sum(bool(r["ranking"]) and r["ranking"][0] in r["gold"] for r in sel), len(sel)


def ms(rows):
    return statistics.median(r["latency_s"] for r in rows) * 1000


def points(tasks, split):
    """Per engine: (median ms, accuracy %) pooled over the given tasks; the baseline's accuracy is returned apart."""
    pts, base = {}, None
    for e in COLORS | {"baseline": 0}:
        rs = [load(f"{e}.{t}") for t in tasks]
        if not all(rs):
            continue
        rows = [r for rr in rs for r in rr]
        hit, n = top1(rows, split)
        if e == "baseline":
            base = 100 * hit / n
        else:
            pts[e] = (statistics.median(r["latency_s"] for r in rows) * 1000, 100 * hit / n)
    return pts, base


PANELS = (("tools", "Tool choice (25 test questions, find_tool's top 10)", ["T"], "TEST"),
          ("building", "Model building (40 block + 30 distribution sentences)", ["blocks", "distributions"], None))


def hero():
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharey=True)
    for ax, (key, title, tasks, split) in zip(axes, PANELS):
        pts, base = points(tasks, split)
        front = frontier(pts)
        fx, fy = [pts[e][0] for e in front], [pts[e][1] for e in front]
        ax.step(fx + [8000], fy + [fy[-1]], where="post", color="#555", lw=1.5, zorder=2)
        for e, (x, y) in pts.items():
            ax.scatter(x, y, s=90, color=KIND_COLOR[KIND.get(e, "encoder (reranker, NLI, embedding)")],
                       marker=MARKER.get(e, "s"), edgecolors="white", linewidths=1.5, zorder=3)
            # A white halo keeps a name readable where the frontier line runs behind it.
            ax.annotate(LABELS[e], (x, y), textcoords="offset points", xytext=OFFSET[key].get(e, (7, 4)), fontsize=9.5, zorder=4,
                        path_effects=[patheffects.withStroke(linewidth=3, foreground="white")])
        ax.axhline(base, ls="--", color="#555", lw=1)
        ax.text(8000 / 1.1, base + 1.2, "keyword search alone (no model)", fontsize=9, color="#555", ha="right")
        ax.set_xscale("log")
        ax.set_xlim(20, 8000)
        ax.set_title(title, fontsize=11.5, fontweight="bold")
        ax.set_xlabel("median latency per decision (ms, log scale; RTX A500 4 GB)", fontsize=10.5)
        ax.tick_params(labelsize=10)
        ax.grid(alpha=0.3, zorder=0)
    axes[0].set_ylabel("top-1 accuracy (%)", fontsize=10.5)
    shapes = [plt.Line2D([], [], ls="", marker=m, color=KIND_COLOR[kind], markersize=8, label=kind) for kind, (m, _) in KINDS.items()]
    shapes.append(plt.Line2D([], [], color="#555", lw=1.5, label="Pareto frontier (nothing is faster and more accurate)"))
    fig.legend(handles=shapes, loc="lower center", ncol=4, fontsize=10, frameon=False)
    fig.suptitle("Engines on naga decisions: faster to the left, more accurate up", fontsize=13)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(OUT / "hero.png", dpi=150)


def chart_data():
    """docs/assets/engines.json for the interactive chart on the docs site (docs/javascripts/pareto.js):
    the same points and panels as hero.png."""
    panels = []
    for key, title, tasks, split in PANELS:
        pts, base = points(tasks, split)
        panels.append({"key": key, "title": title, "baseline": round(base, 1),
                       "points": [{"engine": e, "label": LABELS[e], "kind": KIND.get(e, "encoder (reranker, NLI, embedding)"),
                                   "ms": round(x, 1), "acc": round(y, 1), **({"dx": OFFSET[key][e][0], "dy": OFFSET[key][e][1]} if e in OFFSET[key] else {})}
                                  for e, (x, y) in pts.items()]})
    out = HERE.parents[1] / "docs" / "assets" / "engines.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"kinds": [{"name": k, "color": KIND_COLOR[k], "shape": m} for k, (m, _) in KINDS.items()],
                               "panels": panels}, indent=1) + "\n", encoding="utf-8")


def retries():
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, task in zip(axes, ("blocks", "distributions")):
        n = len([r for r in load(f"retry.tuned.plain.{task}") if r["split"] == "TEST"])
        for i, (e, v, c) in enumerate((("tuned", "plain", "#17becf"), ("tuned", "nudged", "#a6e3ec"),
                                        ("laya", "plain", "#ff7f0e"), ("laya", "nudged", "#ffd0a6"))):
            te = [r for r in load(f"retry.{e}.{v}.{task}") if r["split"] == "TEST"]
            ys = [100 * sum(r["won_at"] is not None and r["won_at"] <= k for r in te) / n for k in (1, 2, 3)]
            ax.bar([k + (i - 1.5) * 0.2 for k in (1, 2, 3)], ys, width=0.2, color=c,
                   label=f"{'fine-tuned gte (encoder)' if e == 'tuned' else 'Laya (System-1)'}, {v}")
        ax.set_title(f"{task} ({n} test rows)", fontsize=10)
        ax.set_xticks([1, 2, 3], ["1 try", "2 tries", "3 tries"])
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("rows right (%)")
    fig.legend(*axes[1].get_legend_handles_labels(), fontsize=8, loc="lower center", ncol=4)
    fig.suptitle("Retrying after a wrong pick: a plain retry beats a nudged one", fontsize=12)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(OUT / "retries.png", dpi=130)


def phase4():
    names = {"tuned": "gte-reranker, fine-tuned\n(encoder)", "gte": "gte-reranker, zero-shot\n(encoder)", "laya": "Laya\n(System-1)"}
    base = {"tuned": "tuned", "gte": "gte-rerank", "laya": "laya"}
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for j, e in enumerate(names):
        rows = [r for r in load(f"phase4.{e}") if r["split"] == "TEST"]
        b = {r["id"]: r for r in load(f"{base[e]}.Tall")}
        hit = lambda rk, r: bool(rk) and rk[0] in r["gold"]
        vals = [sum(hit(b[r["id"]]["ranking"], r) for r in rows), sum(hit(r["a"], r) for r in rows), sum(hit(r["b"], r) for r in rows)]
        for i, (v, c, lab) in enumerate(zip(vals, ("#999999", "#1f77b4", "#d62728"),
                                            ("one stage, all 90 tools", "4a: subset by context", "4b: family, then tool"))):
            ax.bar(j + (i - 1) * 0.26, 100 * v / len(rows), width=0.26, color=c, label=lab if j == 0 else None)
    ax.set_xticks(range(3), list(names.values()))
    ax.set_ylabel("tool choice, TEST top-1 (%)")
    ax.set_title("Offering fewer choices: a subset changes little, two stages are worse", fontsize=11)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "phase4.png", dpi=130)


if __name__ == "__main__":
    # b is slower than a and less accurate: off the frontier; c is slower but more accurate: on it.
    assert frontier({"a": (1, 50), "b": (2, 40), "c": (3, 60)}) == ["a", "c"]
    OUT.mkdir(parents=True, exist_ok=True)
    hero()
    chart_data()
    retries()
    phase4()
