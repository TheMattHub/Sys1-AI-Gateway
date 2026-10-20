"""The Claude Code routing study, rerun on the public seed sets (stdlib, any Python 3.11+):

    python bench/routing/routing.py run <engine> <provider> [key=value ...]   # one engine, through the gateway
    python bench/routing/routing.py report                                  # the table in docs/studies

Seeds: calibration/routing-seed.jsonl (45 prompts, teacher tier labels) and calibration/yes-no-seed.jsonl (24
tool calls, "is this destructive?"). Each engine answers through its gateway provider exactly as the hooks ask:
- direct choice: route_hook.request_for, the retired "which model?" question over the three TIERS;
- features: routing_features.requests_for, the four yes/no questions in one decide_many pass, then
  routing_rule.tier; a feature the engine fails to answer leaves the tier empty, counted as wrong;
- yes/no: the destructive-call question as a two-option choice.
Everything is asked at min_confidence 0, so the numbers are first answers, not abstentions. Writes
bench/routing/results/<engine>.json with aggregates and each seed row's answers (the seeds are public)."""
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from system1_gateway.config import Config  # noqa: E402
from system1_gateway.gateway import Gateway  # noqa: E402
from system1_gateway.route_hook import TIERS, request_for  # noqa: E402
from system1_gateway.routing_features import requests_for  # noqa: E402
from system1_gateway.routing_rule import tier as rule_tier  # noqa: E402

RES = Path(__file__).resolve().parent / "results"


def seeds(name):
    return [json.loads(x) for x in (ROOT / "calibration" / name).read_text(encoding="utf-8").splitlines() if x.strip()]


def run(engine, provider, settings):
    g = Gateway(Config(provider=provider, min_confidence=0.0, timeout_s=120, providers={provider: settings}))
    if g.config_errors:
        raise SystemExit(f"config: {g.config_errors}")
    rows, ms = [], {"direct": [], "features": [], "yes_no": []}
    for e in seeds("routing-seed.jsonl"):
        t0 = time.perf_counter()
        r = g.decide(request_for(e["prompt"], 0.0))
        ms["direct"].append(time.perf_counter() - t0)
        direct = r["decision"].split(":", 1)[0] if r["status"] == "decided" else None
        t0 = time.perf_counter()
        feats = g.decide_many(requests_for(e["prompt"], 0.0))
        ms["features"].append(time.perf_counter() - t0)
        answers = {k: f["decision"] if f["status"] == "decided" else None for k, f in feats.items()}
        rows.append({"label": e["label"], "direct": direct, "rule": rule_tier(answers), "features": answers,
                     "errors": sorted({(f.get("error") or {}).get("code") for f in [r, *feats.values()] if f.get("error")})})
    yn = []
    for e in seeds("yes-no-seed.jsonl"):
        t0 = time.perf_counter()
        r = g.decide({"question": e["question"], "options": ["yes", "no"], "context": e["context"], "min_confidence": 0.0})
        ms["yes_no"].append(time.perf_counter() - t0)
        yn.append({"label": e["label"], "answer": r["decision"] if r["status"] == "decided" else None})
    n = len(rows)
    out = {"engine": engine, "provider": provider, "n_routing": n, "n_yes_no": len(yn),
           "direct": sum(r["direct"] == r["label"] for r in rows), "rule": sum(r["rule"] == r["label"] for r in rows),
           "always_sonnet": sum(r["label"] == "sonnet" for r in rows),
           "direct_unanswered": sum(r["direct"] is None for r in rows), "rule_unanswered": sum(r["rule"] is None for r in rows),
           "yes_no": sum(r["answer"] == r["label"] for r in yn), "yes_no_unanswered": sum(r["answer"] is None for r in yn),
           "median_ms": {k: round(statistics.median(v) * 1000) for k, v in ms.items()}, "rows": rows, "yes_no_rows": yn}
    RES.mkdir(exist_ok=True)
    (RES / f"{engine}.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"{engine}: direct {out['direct']}/{n}, features+rule {out['rule']}/{n}, yes/no {out['yes_no']}/{len(yn)}, "
          f"ms {out['median_ms']}")


def report():
    # "below" = a tier under the label (or none): the unsafe miss, a too-small model for the task.
    rank = {"haiku": 0, "sonnet": 1, "opus": 2}
    below = lambda rows, k: sum(rank.get(x[k], -1) < rank[x["label"]] for x in rows)  # noqa: E731
    print("| engine | provider | direct choice | below | features + rule | below | yes/no (destructive) | "
          "median ms: direct / features / yes-no |")
    print("|---|---|---|---|---|---|---|---|")
    base = None
    for p in sorted(RES.glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        base = base or (r["always_sonnet"], r["n_routing"])
        miss = lambda k: f" ({r[k + '_unanswered']} unanswered)" if r[k + "_unanswered"] else ""  # noqa: E731
        m = r["median_ms"]
        print(f"| {r['engine']} | {r['provider']} | {r['direct']}/{r['n_routing']}{miss('direct')} | {below(r['rows'], 'direct')} | "
              f"{r['rule']}/{r['n_routing']}{miss('rule')} | {below(r['rows'], 'rule')} | {r['yes_no']}/{r['n_yes_no']}{miss('yes_no')} | "
              f"{m['direct']} / {m['features']} / {m['yes_no']} |")
    if base:
        print(f"\nAlways answering sonnet: {base[0]}/{base[1]}.")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3], dict(a.split("=", 1) for a in sys.argv[4:]))
    else:
        report()
