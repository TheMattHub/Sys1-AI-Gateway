"""Is a System-1 engine ready to route? Scores the text features and the tier rule on labeled log entries.

    python scripts/evaluate.py [--provider NAME] [--log PATH] [--min-feature-accuracy 0.85]
                               [--min-safety 0.95] [--min-failures 30] [--json]

Read-only. For every routing-log entry with feature labels (teacher, spot-checked by the user) or an outcome
(scripts/outcomes.py), the engine is asked the features in one decide_many pass, as the hooks do.
- features: accuracy, AUROC, and coverage/accuracy at the routing threshold, against the feature labels
- rule: on outcome-labeled spawns, safety = share of failed spawns where the rule tier is above the tier that
  failed; agreement = share of succeeded spawns where it is at or below the tier that succeeded; savings =
  share of succeeded spawns where it is below. Shown with the engine's answers and with the teacher's
  feature labels (the rule's ceiling), so a weak rule and a weak engine can be told apart.
READY only if every feature reaches --min-feature-accuracy at the threshold, safety >= --min-safety, and at
least --min-failures failed spawns are labeled. Prints aggregates only, never prompt text.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from system1_gateway.config import ConfigError, load_config  # noqa: E402
from system1_gateway.gateway import Gateway  # noqa: E402
from system1_gateway.routing_features import FEATURES, ask_features  # noqa: E402
from system1_gateway.routing_rule import tier as rule_tier  # noqa: E402

RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}


def auroc(pairs) -> float | None:
    """P(confidence of a right answer > confidence of a wrong one); None without both kinds."""
    pos = [c for c, ok in pairs if ok]
    neg = [c for c, ok in pairs if not ok]
    if not pos or not neg:
        return None
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def feature_scores(rows, threshold: float) -> dict:
    """rows: (answer or None, confidence or None, label)."""
    pairs = [(conf or 0.0, answer == label) for answer, conf, label in rows]
    kept = [ok for (conf, ok) in pairs if conf >= threshold]
    return {"n": len(pairs), "accuracy": sum(ok for _, ok in pairs) / len(pairs) if pairs else None,
            "auroc": auroc(pairs), "coverage_at_threshold": len(kept) / len(pairs) if pairs else None,
            "accuracy_at_threshold": sum(kept) / len(kept) if kept else None}


def rule_scores(rows) -> dict:
    """rows: (rule tier or None, outcome, tier that ran). An unanswered rule tier counts as unsafe."""
    failed = [(r, t) for r, o, t in rows if o == "failed" and t in RANK]
    succeeded = [(r, t) for r, o, t in rows if o == "succeeded" and t in RANK]

    def share(items, test):
        return sum(1 for r, t in items if r in RANK and test(RANK[r], RANK[t])) / len(items) if items else None
    return {"failed": len(failed), "succeeded": len(succeeded),
            "safety": share(failed, lambda r, t: r > t),
            "agreement": share(succeeded, lambda r, t: r <= t),
            "savings": share(succeeded, lambda r, t: r < t)}


def verdict(features: dict, rule: dict, bars: dict):
    why = []
    for k in FEATURES:  # every feature must be measured: one missing from the labels is unmet, not skipped
        acc = (features.get(k) or {}).get("accuracy_at_threshold")
        if k not in features:
            why.append(f"{k}: no feature labels")
        elif acc is None or acc < bars["min_feature_accuracy"]:
            why.append(f"{k}: accuracy at threshold {acc if acc is None else round(acc, 2)} < {bars['min_feature_accuracy']}")
    if rule["failed"] < bars["min_failures"]:
        why.append(f"only {rule['failed']} failed spawns labeled (need {bars['min_failures']})")
    if rule["safety"] is None or rule["safety"] < bars["min_safety"]:
        why.append(f"rule safety {rule['safety']} < {bars['min_safety']}")
    return not why, why


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider")
    ap.add_argument("--log", type=Path)
    ap.add_argument("--min-feature-accuracy", type=float, default=0.85)
    ap.add_argument("--min-safety", type=float, default=0.95)
    ap.add_argument("--min-failures", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"config error: {e}")
        return 1
    if args.provider:
        cfg.provider, cfg.fallback = args.provider, []
    cfg.timeout_s = max(cfg.timeout_s, 30.0)  # an evaluation isn't the hook: slow engines still get scored
    cfg.pause_file = ""  # the pause switch is for live hooks, not for testing
    gateway = Gateway(cfg)
    if gateway.config_errors:
        print("config error: " + "; ".join(gateway.config_errors))
        return 1
    threshold = cfg.routing_min_confidence if cfg.routing_min_confidence is not None else cfg.min_confidence
    log = args.log or Path(cfg.routing_log_file).expanduser()
    entries = []
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        print(f"cannot read the routing log {log}: {e}")
        return 1
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and isinstance(e.get("prompt"), str) and e.get("source") != "skill" and (
                isinstance(e.get("feature_labels"), dict)
                or (e.get("source") == "agent" and e.get("outcome") in ("succeeded", "failed"))):
            entries.append(e)

    per_feature = {k: [] for k in FEATURES}
    rule_engine, rule_teacher, latencies = [], [], []
    for e in entries:
        started = time.monotonic()
        answers = ask_features(gateway, e["prompt"])
        latencies.append(time.monotonic() - started)
        labels = e.get("feature_labels") if isinstance(e.get("feature_labels"), dict) else {}
        for k in FEATURES:
            if labels.get(k) in ("yes", "no"):
                per_feature[k].append((answers[k]["answer"], answers[k]["confidence"], labels[k]))
        if e.get("outcome") in ("succeeded", "failed"):
            rule_engine.append((rule_tier({k: v["answer"] for k, v in answers.items()}), e["outcome"], e.get("outcome_tier")))
            if all(labels.get(k) in ("yes", "no") for k in ("design", "review", "read_only")):
                rule_teacher.append((rule_tier(labels), e["outcome"], e.get("outcome_tier")))

    features = {k: feature_scores(rows, threshold) for k, rows in per_feature.items() if rows}
    engine, teacher = rule_scores(rule_engine), rule_scores(rule_teacher)
    bars = {"min_feature_accuracy": args.min_feature_accuracy, "min_safety": args.min_safety,
            "min_failures": args.min_failures}
    ready, why = verdict(features, engine, bars) if features else (False, ["no feature labels yet"])
    latencies.sort()
    report = {"provider": cfg.provider, "model": gateway.chain[0].capabilities().get("model"),
              "n_entries": len(entries), "threshold": threshold, "features": features,
              "rule_engine": engine, "rule_teacher": teacher, "ready": ready, "unmet": why,
              "latency_p50_s": latencies[len(latencies) // 2] if latencies else None,
              "latency_p90_s": latencies[int(len(latencies) * 0.9)] if latencies else None}
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    def pct(x):
        return "-" if x is None else f"{x:.0%}"
    print(f"{report['provider']} ({report['model']}): {len(entries)} labeled entries, threshold {threshold}, "
          f"latency p50 {report['latency_p50_s'] or 0:.2f}s p90 {report['latency_p90_s'] or 0:.2f}s")
    for k, s in features.items():
        print(f"  {k:10} n={s['n']:<4} accuracy {pct(s['accuracy'])}  AUROC {s['auroc'] if s['auroc'] is None else round(s['auroc'], 2)}"
              f"  at threshold: {pct(s['coverage_at_threshold'])} covered, {pct(s['accuracy_at_threshold'])} right")
    for name, s in (("rule (engine)", engine), ("rule (teacher)", teacher)):
        print(f"  {name:15} failed {s['failed']}, succeeded {s['succeeded']}: safety {pct(s['safety'])}, "
              f"agreement {pct(s['agreement'])}, savings {pct(s['savings'])}")
    print("READY" if ready else "NOT READY: " + "; ".join(why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
