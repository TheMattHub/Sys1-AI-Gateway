"""Charts and the engine table for the README and the study page, from the tool-choice results over all 90 tools
on TEST3 (distill/results3, split TEST3) and AGENT3 (distill/results4). Needs matplotlib.

    python bench/naga/plot.py        # writes docs/screenshots/{hero,retries}.png, docs/assets/engines.json,
                                     # and prints the engine table (Markdown) for the study page

hero.png and engines.json: top-1 accuracy against median latency per engine, one panel per set.
retries.png: right within 1, 2 and 3 tries against the time those tries take, one line per engine.
"""
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import patheffects  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "docs" / "screenshots"
SETS = (("TEST3", "TEST3: 150 requests by four writers", HERE / "distill" / "results3"),
        ("AGENT3", "AGENT3: 274 find_tool queries written by the agent", HERE / "distill" / "results4"))

# What kind of model each engine is, drawn as the point's shape and colour: System-1 decision models (built to
# answer a multiple-choice question in one pass), encoders (rerankers and embeddings, the trained students
# among them) and LLMs. Three hues validated with the dataviz skill's palette checks, light and dark.
S1, ENC, LLM = "System-1 decision model", "encoder (reranker, embedding)", "LLM"
KINDS = {S1: ("o", "#eb6834"), ENC: ("s", "#2a78d6"), LLM: ("^", "#1baf7a")}
ENGINES = {"harrier-bi": ("harrier (bi-encoder)", ENC), "gte-rerank": ("gte-reranker, untuned", ENC),
           "qwen3-rerank": ("Qwen3-Reranker-0.6B", ENC), "tuned-r1": ("gte, tuned on 54 questions", ENC),
           "gte-gemma4": ("gte <- Gemma labels", ENC), "gte-haiku": ("gte <- Haiku labels", ENC),
           "gte-opus": ("gte <- Opus labels", ENC), "gte-agreed": ("gte <- agreed labels", ENC),
           "laya": ("Laya", S1), "d1-omni": ("d1-omni-600M", S1), "d1-3b": ("d1-3B (Q8_0)", S1),
           "anyjev": ("AnyJev on Qwen3-1.7B", S1), "openthai-ollama": ("OpenThai (Ollama build)", S1),
           "gemma4": ("Gemma 4 E4B", LLM), "haiku": ("Claude Haiku 5.5 (API)", LLM), "opus": ("Claude Opus 5.5 (API)", LLM)}
XMIN, XMAX = 20, 30000

# Label offsets (points, y up) where engines sit close together; shared with the interactive chart.
OFFSET = {"TEST3": {"gte-opus": (-60, 8), "gte-agreed": (-128, -4), "gte-haiku": (-118, -6), "opus": (8, -13),
                    "haiku": (-96, 6), "d1-3b": (-30, 8), "qwen3-rerank": (8, 4), "gemma4": (8, -6),
                    "tuned-r1": (8, 2), "gte-rerank": (8, -12), "harrier-bi": (8, 6), "openthai-ollama": (8, -12)},
          "AGENT3": {"gte-opus": (-112, 3), "gte-agreed": (-120, -8), "gte-haiku": (-112, -8), "tuned-r1": (8, -16),
                     "opus": (8, 4), "haiku": (-118, 4), "gemma4": (8, 5), "gte-rerank": (8, -4),
                     "gte-gemma4": (8, -6), "harrier-bi": (8, -12),
                     "qwen3-rerank": (8, 4)}}
YLIM = (15, 75)
# The engines the study's text names stand out in the retries chart; the rest are drawn faint, unlabelled.
RETRY_OFFSET = {"TEST3": {"gte-opus": (-118, -3)}, "AGENT3": {"haiku": (-128, 2), "gte-opus": (6, -9)}}
NAMED = ("laya", "d1-omni", "gte-rerank", "gte-opus", "d1-3b", "gemma4", "haiku", "opus")


def load(engine, key):
    """The engine's rows over all 90 tools on one set, or None when it was not run there."""
    d = dict((k, p) for k, _, p in SETS)[key]
    p = d / f"{engine}.Tall.jsonl"
    if not p.exists():
        return None
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if r["split"] == key] if key == "TEST3" else rows


def rank(r):
    """Tries needed: 1 + the position of the first accepted label in the ranking, None when it is not there."""
    return next((i + 1 for i, x in enumerate(r["ranking"]) if x in r["gold"]), None)


def within(rows, k):
    return sum((rank(r) or k + 1) <= k for r in rows)


def ms(rows):
    return statistics.median(r["latency_s"] for r in rows) * 1000


def frontier(pts):
    """The engines no other engine beats on both speed and accuracy, fastest first: walk by latency and
    keep each one more accurate than every faster one."""
    out, best = [], float("-inf")
    for e, (x, y) in sorted(pts.items(), key=lambda kv: (kv[1][0], -kv[1][1])):
        if y > best:
            out.append(e)
            best = y
    return out


def points(key):
    pts = {}
    for e in ENGINES:
        rows = load(e, key)
        if rows:
            pts[e] = (ms(rows), 100 * within(rows, 1) / len(rows))
    base = load("baseline", key)
    return pts, 100 * within(base, 1) / len(base)


def style(ax):
    ax.set_xscale("log")
    ax.set_xlim(XMIN, XMAX)
    ax.tick_params(labelsize=10)
    ax.grid(alpha=0.3, zorder=0)


def legend(fig, extra, ncol=4):
    shapes = [plt.Line2D([], [], ls="", marker=m, color=c, markersize=8, label=k) for k, (m, c) in KINDS.items()]
    fig.legend(handles=shapes + extra, loc="lower center", ncol=ncol, fontsize=10, frameon=False)


def halo():
    # A white halo keeps a name readable where a line runs behind it.
    return [patheffects.withStroke(linewidth=3, foreground="white")]


def hero():
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8), sharey=True)
    for ax, (key, title, _) in zip(axes, SETS):
        pts, base = points(key)
        front = frontier(pts)
        fx, fy = [pts[e][0] for e in front], [pts[e][1] for e in front]
        ax.step(fx + [XMAX], fy + [fy[-1]], where="post", color="#555", lw=1.5, zorder=2)
        for e, (x, y) in pts.items():
            m, c = KINDS[ENGINES[e][1]]
            ax.scatter(x, y, s=90, color=c, marker=m, edgecolors="white", linewidths=1.5, zorder=3)
            ax.annotate(ENGINES[e][0], (x, y), textcoords="offset points", xytext=OFFSET[key].get(e, (7, 4)),
                        fontsize=9, zorder=4, path_effects=halo())
        ax.axhline(base, ls="--", color="#555", lw=1)
        ax.text(XMAX / 1.1, base + 1.2, "find_tool alone (keyword search)", fontsize=9, color="#555", ha="right")
        style(ax)
        ax.set_ylim(*YLIM)
        ax.set_title(f"{title}, all 90 tools", fontsize=11.5, fontweight="bold")
        ax.set_xlabel("median latency per decision (ms, log scale; RTX A500 4 GB)", fontsize=10.5)
    axes[0].set_ylabel("right first time, top-1 (%)", fontsize=10.5)
    legend(fig, [plt.Line2D([], [], color="#555", lw=1.5, label="Pareto frontier (nothing is faster and more accurate)")])
    fig.suptitle("Which engine picks naga's tool: faster to the left, more accurate up", fontsize=13)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(OUT / "hero.png", dpi=150)


def chart_data():
    """docs/assets/engines.json for the interactive chart (docs/javascripts/pareto.js): hero.png's points."""
    panels = []
    for key, title, _ in SETS:
        pts, base = points(key)
        panels.append({"key": key, "title": f"{title}, all 90 tools", "baseline": round(base, 1),
                       "points": [{"engine": e, "label": ENGINES[e][0], "kind": ENGINES[e][1], "ms": round(x, 1),
                                   "acc": round(y, 1), **({"dx": OFFSET[key][e][0], "dy": OFFSET[key][e][1]} if e in OFFSET[key] else {})}
                                  for e, (x, y) in pts.items()]})
    out = HERE.parents[1] / "docs" / "assets" / "engines.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"kinds": [{"name": k, "color": c, "shape": m} for k, (m, c) in KINDS.items()],
                               "panels": panels}, indent=1) + "\n", encoding="utf-8")


def tries(rows, k):
    """Mean tries used when a request stops at its first right answer or after k tries."""
    return statistics.mean(min(rank(r) or k, k) for r in rows)


def retries():
    """Right within 1, 2 and 3 tries against the time they take: median decision time x mean tries used. Try k
    is right when the gold is in the first k of the engine's ranking (round 2: a plain retry gives exactly that)."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.2), sharey=True)
    for ax, (key, title, _) in zip(axes, SETS):
        best = max(ENGINES, key=lambda e: within(load(e, key) or [], 1) / len(load(e, key) or [0]))
        rows = load(best, key)
        ax.axhline(100 * within(rows, 1) / len(rows), ls=":", color="#555", lw=1)
        for e, (label, kind) in ENGINES.items():
            rows = load(e, key)
            if not rows:
                continue
            m, c = KINDS[kind]
            on = e in NAMED
            xs = [ms(rows) * tries(rows, k) for k in (1, 2, 3)]
            ys = [100 * within(rows, k) / len(rows) for k in (1, 2, 3)]
            ax.plot(xs, ys, color=c, lw=1.6 if on else 0.8, alpha=1 if on else 0.3, zorder=3 if on else 2)
            ax.scatter(xs, ys, s=[30, 30, 60], color=c, marker=m, edgecolors="white", linewidths=1,
                       alpha=1 if on else 0.3, zorder=3 if on else 2)
            if on:
                ax.annotate(label, (xs[-1], ys[-1]), textcoords="offset points", xytext=RETRY_OFFSET[key].get(e, (6, -3)),
                            fontsize=9, zorder=4, path_effects=halo())
        style(ax)
        ax.set_title(f"{title}, all 90 tools", fontsize=11.5, fontweight="bold")
        ax.set_xlabel("time for the tries used (ms, log scale): median decision time x mean tries", fontsize=10)
    axes[0].set_ylabel("right within 1, 2, 3 tries (%)", fontsize=10.5)
    legend(fig, [plt.Line2D([], [], color="#555", lw=1.2, marker="o", markersize=4,
                            label="one engine: 1, 2, 3 tries (big mark = 3; faint = not named in the text)"),
                 plt.Line2D([], [], color="#555", lw=1, ls=":", label="the best engine's first try")], ncol=3)
    fig.suptitle("Retrying: can a fast engine catch a slower, better one?", fontsize=13)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    fig.savefig(OUT / "retries.png", dpi=150)


def table():
    """The study page's engine table: top-1 and top-3 on both sets, median ms on AGENT3 (TEST3 where missing)."""
    print("| engine | kind | TEST3 top-1 | TEST3 top-3 | AGENT3 top-1 | AGENT3 top-3 | median ms |")
    print("|---|---|---|---|---|---|---|")
    for e, (label, kind) in {"baseline": ("`find_tool` alone", "keyword search"), **ENGINES}.items():
        t, a = load(e, "TEST3"), load(e, "AGENT3")
        cell = lambda rows, k: f"{within(rows, k)}/{len(rows)}" if rows else "not run"
        print(f"| {label} | {kind.split(' (')[0]} | {cell(t, 1)} | {cell(t, 3)} | {cell(a, 1)} | {cell(a, 3)} | "
              f"{ms(a or t):,.0f} |")


if __name__ == "__main__":
    # b is slower than a and less accurate: off the frontier; c is slower but more accurate: on it.
    assert frontier({"a": (1, 50), "b": (2, 40), "c": (3, 60)}) == ["a", "c"]
    # Gold second: right within 2 and 3 tries, not 1; two tries used of up to 3, one of up to 1.
    r = [{"ranking": ["x", "g"], "gold": ["g"]}]
    assert (within(r, 1), within(r, 2), tries(r, 3), tries(r, 1)) == (0, 1, 2, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    hero()
    chart_data()
    retries()
    table()
