"""Fit a temperature for the configured System-1 provider from labeled decisions, and report reliability.

    <gateway venv python> scripts/calibrate.py DATA.jsonl [--target-accuracy 0.8] [--write | --ship] [--json]

DATA.jsonl lines are either routing-log entries ({"prompt": ..., "label": "haiku" | "sonnet" | "opus"}, as
written by the routing hook) or generic decisions ({"question": ..., "options": [...], "context": {...},
"label": <one option, or "yes"/"no" without options>}). Lines without a label are skipped.

Each example is re-asked live, with calibration off, so the fit always matches the running provider and
model. One temperature is fitted per question asked at least MIN_GROUP times (e.g. routing), plus one per
option count as the fallback for other questions. Temperature never changes which answer wins, so if
accuracy itself is too low, calibration can't fix it: improve the question/options, or fine-tune the model.

--write  merge the fit into ~/.system1-gateway/calibration.json (this machine)
--ship   merge it into system1_gateway/calibration.json (commit it so every install gets it)
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run from a clone or the plugin copy

from system1_gateway import calibration  # noqa: E402
from system1_gateway.config import load_config  # noqa: E402
from system1_gateway.gateway import Gateway  # noqa: E402
from system1_gateway.route_hook import TIERS, request_for  # noqa: E402
from system1_gateway.routing_features import FEATURES, requests_for  # noqa: E402

MIN_GROUP = 10  # fewer samples than this give a meaningless fit
THRESHOLDS = [round(0.30 + 0.05 * i, 2) for i in range(14)]  # 0.30 .. 0.95


def to_request(entry: dict):
    """(gateway request, label answer) or None if the entry is unlabeled or unusable."""
    label = entry.get("label")
    if not isinstance(label, str) or not label.strip() or entry.get("source") == "skill":
        return None  # skill-picker entries are labeled with skill names, not tiers
    if "prompt" in entry:  # routing log
        tier = next((t for t in TIERS if t.split(":", 1)[0] == label.strip().lower()), None)
        return (request_for(entry["prompt"], 0.0), tier) if tier else None
    if "question" in entry:
        req = {"question": entry["question"], "min_confidence": 0.0}
        for key in ("options", "context"):
            if key in entry:
                req[key] = entry[key]
        return req, label
    return None


def feature_requests(entry: dict) -> list:
    """(gateway request, "yes"/"no") for every labeled text feature of a routing-log entry."""
    labels = entry.get("feature_labels")
    if entry.get("source") == "skill" or not isinstance(labels, dict) or not isinstance(entry.get("prompt"), str):
        return []
    reqs = requests_for(entry["prompt"], 0.0)
    return [(reqs[k], v) for k, v in labels.items() if k in FEATURES and v in ("yes", "no")]


def nll(samples, t):
    return -sum(math.log(max(calibration.scale(p, t)[y], 1e-12)) for p, y in samples) / len(samples)


def fit_temperature(samples) -> float:
    """Golden-section search on log T for the lowest negative log-likelihood (NLL is unimodal in T)."""
    lo, hi = math.log(0.05), math.log(20.0)
    g = (math.sqrt(5) - 1) / 2
    a, b = hi - g * (hi - lo), lo + g * (hi - lo)
    fa, fb = nll(samples, math.exp(a)), nll(samples, math.exp(b))
    for _ in range(60):
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - g * (hi - lo)
            fa = nll(samples, math.exp(a))
        else:
            lo, a, fa = a, b, fb
            b = lo + g * (hi - lo)
            fb = nll(samples, math.exp(b))
    return round(math.exp((lo + hi) / 2), 4)


def metrics(samples, t: float, target: float) -> dict:
    rows = []
    for p, y in samples:
        q = calibration.scale(p, t)
        top = max(q, key=q.get)
        rows.append((q[top], top == y))
    n = len(rows)
    ece = 0.0
    for i in range(10):  # 10 equal-width confidence bins
        b = [r for r in rows if i / 10 < r[0] <= (i + 1) / 10 or (i == 0 and r[0] == 0)]
        if b:
            ece += len(b) / n * abs(sum(c for c, _ in b) / len(b) - sum(ok for _, ok in b) / len(b))
    right = [c for c, ok in rows if ok]
    wrong = [c for c, ok in rows if not ok]
    auroc = (sum((r > w) + 0.5 * (r == w) for r in right for w in wrong) / (len(right) * len(wrong))
             if right and wrong else None)
    table = []
    for th in THRESHOLDS:
        kept = [ok for c, ok in rows if c >= th]
        table.append({"threshold": th, "coverage": round(len(kept) / n, 3),
                      "accuracy": round(sum(kept) / len(kept), 3) if kept else None, "n": len(kept)})
    # Lowest threshold that meets the target on enough examples to mean something.
    ok = [r for r in table if r["accuracy"] is not None and r["accuracy"] >= target and r["n"] >= max(5, 0.1 * n)]
    return {"n": n, "accuracy": round(sum(ok for _, ok in rows) / n, 3), "nll": round(nll(samples, t), 4),
            "ece": round(ece, 3), "auroc": round(auroc, 3) if auroc is not None else None,
            "recommended_threshold": ok[0]["threshold"] if ok else None, "selective": table}


def merge(path: Path, new_entries: list):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"entries": []}
    key = lambda e: (e.get("provider"), e.get("model"), e.get("question"), e.get("n_options"))  # noqa: E731
    fresh = {key(e) for e in new_entries}
    data["entries"] = [e for e in data.get("entries", []) if key(e) not in fresh] + new_entries
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data", type=Path)
    ap.add_argument("--target-accuracy", type=float, default=0.8)
    dest = ap.add_mutually_exclusive_group()
    dest.add_argument("--write", action="store_true", help="save to ~/.system1-gateway/calibration.json")
    dest.add_argument("--ship", action="store_true", help="save to the packaged system1_gateway/calibration.json")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args()

    gateway = Gateway(load_config(), calibration=[])  # raw provider probabilities
    if gateway.config_errors:
        sys.exit("config error: " + "; ".join(gateway.config_errors))
    provider = gateway.chain[0]
    model = provider.capabilities().get("model")

    lines = [json.loads(l) for l in args.data.read_text(encoding="utf-8").splitlines() if l.strip()]
    groups, skipped, failed = {}, 0, []
    for entry in lines:
        items = ([] if (one := to_request(entry)) is None else [one]) + feature_requests(entry)
        if not items:
            skipped += 1
            continue
        for req, label in items:
            result = gateway.decide(req)
            probs = result.get("probabilities")
            if result["status"] == "error" or not probs or label not in probs or result["provider"] != provider.name:
                failed.append({"entry": entry.get("prompt") or entry.get("question"),
                               "why": (result.get("error") or {}).get("message") or "no probabilities for the label"})
                continue
            groups.setdefault((req["question"], len(probs)), []).append((probs, label))

    fits, report = [], {"provider": provider.name, "model": model, "skipped_unlabeled": skipped,
                        "failed": failed, "fits": []}
    # A question asked often enough gets its own fit. The per-option-count fallback learns only from the
    # rest (rarely repeated questions), so one well-covered question can't set the temperature for others.
    leftovers = {}
    for (question, n_opt), samples in groups.items():
        if len(samples) >= MIN_GROUP:
            fits.append((question, n_opt, samples))
        else:
            leftovers.setdefault(n_opt, []).extend(samples)
    fits += [(None, n_opt, s) for n_opt, s in leftovers.items() if len(s) >= MIN_GROUP]

    entries = []
    for question, n_opt, samples in fits:
        t = fit_temperature(samples)
        before, after = metrics(samples, 1.0, args.target_accuracy), metrics(samples, t, args.target_accuracy)
        report["fits"].append({"question": question, "n_options": n_opt, "temperature": t,
                               "before": before, "after": after})
        entries.append({"provider": provider.name, "model": model, "question": question, "n_options": n_opt,
                        "temperature": t, "n_samples": len(samples), "fitted_at": time.strftime("%Y-%m-%d"),
                        "data": args.data.name,
                        "accuracy": after["accuracy"], "ece_before": before["ece"], "ece_after": after["ece"],
                        "recommended_threshold": after["recommended_threshold"]})

    if entries and (args.write or args.ship):
        path = calibration.USER_FILE if args.write else calibration.SHIPPED_FILE
        merge(path, entries)
        report["written_to"] = str(path)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print(f"provider {provider.name} / model {model}: {sum(len(s) for s in groups.values())} usable, "
          f"{skipped} unlabeled, {len(failed)} failed")
    for f in failed[:5]:
        print(f"  failed: {str(f['entry'])[:60]!r}: {f['why']}")
    if not fits:
        print(f"Not enough data: every fit needs at least {MIN_GROUP} labeled examples.")
    for fit in report["fits"]:
        b, a = fit["before"], fit["after"]
        scope = (f"question {fit['question'][:60]!r}" if fit["question"]
                 else f"fallback for other {fit['n_options']}-option questions")
        print(f"\n== {scope}: n={a['n']}, T={fit['temperature']}")
        print(f"   accuracy {a['accuracy']:.0%} (temperature can't change this)   AUROC {a['auroc']}")
        print(f"   ECE {b['ece']} -> {a['ece']}   NLL {b['nll']} -> {a['nll']}")
        print(f"   recommended min_confidence for >= {args.target_accuracy:.0%} accuracy: {a['recommended_threshold']}")
        print("   threshold  coverage  accuracy")
        for r in a["selective"]:
            if r["n"]:
                print(f"     {r['threshold']:.2f}      {r['coverage']:6.0%}    {r['accuracy']:.0%}  (n={r['n']})")
    if "written_to" in report:
        print(f"\nSaved to {report['written_to']}")


if __name__ == "__main__":
    main()
