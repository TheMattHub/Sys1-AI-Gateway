"""Is the System-1 gateway used across Claude Code sessions, and what does it save? Read-only, aggregates only.

    python scripts/usage_report.py [--days 14] [--json] [--projects-dir ~/.claude/projects]

Source: Claude Code's own session transcripts (~/.claude/projects/<project>/<session>.jsonl), which record every
prompt, every hook hint (as an attachment) and every Agent spawn, plus each subagent's transcript
(<session>/subagents/agent-*.jsonl, linked by toolUseId in agent-*.meta.json) with per-message token usage.
The output holds counts, rates and costs only: never prompt or task text.

A routing hint belongs to the turn of the prompt it was attached to. A spawn in that turn "followed" the hint
if its tier matches; otherwise it was an upgrade or a downgrade. Spawns in turns without a hint form the
baseline mix. Costs are API list prices from prices.json (a yardstick: Claude Code subscriptions bill differently).
- realised savings: for spawns that followed a hint, the cost of the same tokens at the baseline tier mix minus
  the actual cost
- missed savings: for spawns upgraded past the hint, the actual cost minus the cost at the hinted tier
ponytail: tokens are repriced as-is (tokenizers differ slightly between models), and nested subagents
(spawned by subagents) are counted in totals but never tied to hints.
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from system1_gateway import calibration  # noqa: E402
from system1_gateway.config import ConfigError, load_config  # noqa: E402
from system1_gateway.session_hook import CALIBRATE_EVERY, unlabeled_count  # noqa: E402

TIER_ORDER = ["haiku", "sonnet", "opus", "fable"]
HINT_RE = re.compile(r"System-1 routing hint \((\w+), confidence ([0-9.]+)\).*?\*\*(\w+)\*\*", re.S)
HINT_WINDOW_S = 60  # a hint's attachment lands within seconds of its prompt
HINT_TOKENS = 70


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def tier_of(model: str | None, main_tier: str | None) -> str | None:
    m = (model or "inherit").lower()
    if m == "inherit":
        return main_tier
    return next((t for t in TIER_ORDER if t in m or (t == "fable" and "mythos" in m)), None)


class Prices:
    def __init__(self, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.models = data["models"]
        self.tiers = {k: v for k, v in data["tiers"].items() if k in TIER_ORDER}

    def rates(self, model: str):
        key = max((k for k in self.models if model.startswith(k)), key=len, default=None)
        return self.models[key] if key else None

    def cost(self, usage: dict, model: str) -> float | None:
        r = self.rates(model)
        if r is None:
            return None
        cc = usage.get("cache_creation") or {}
        write_1h = cc.get("ephemeral_1h_input_tokens", 0) or 0
        write_5m = (usage.get("cache_creation_input_tokens", 0) or 0) - write_1h
        return (usage.get("input_tokens", 0) * r["input"] + usage.get("output_tokens", 0) * r["output"]
                + (usage.get("cache_read_input_tokens", 0) or 0) * r["cache_read"]
                + write_5m * r["cache_write"] + write_1h * 2 * r["input"]) / 1e6


def read_jsonl(path: Path):
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def subagent_usage(session_dir: Path) -> dict:
    """toolUseId -> list of (usage, model) for every message the spawned subagent billed."""
    out = {}
    sub = session_dir / "subagents"
    if not sub.is_dir():
        return out
    for meta in sub.glob("*.meta.json"):
        try:
            tool_use_id = json.loads(meta.read_text(encoding="utf-8")).get("toolUseId")
        except (OSError, ValueError):
            continue
        rows = []
        for d in read_jsonl(meta.with_name(meta.name.replace(".meta.json", ".jsonl"))):
            msg = d.get("message") or {}
            if d.get("type") == "assistant" and msg.get("usage") and msg.get("model"):
                rows.append((msg["usage"], msg["model"]))
        if tool_use_id:
            out[tool_use_id] = rows
    return out


def starts_turn(d: dict) -> bool:
    """A user-side message that isn't a tool result: a human prompt, a task notification, a peer message..."""
    if d.get("type") != "user" or d.get("isSidechain"):
        return False
    content = (d.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    return isinstance(content, list) and not any(isinstance(c, dict) and c.get("type") == "tool_result"
                                                 for c in content)


def is_human(d: dict) -> bool:
    origin = d.get("origin")
    kind = origin.get("kind") if isinstance(origin, dict) else origin
    return kind == "human" or (kind is None and not d.get("isMeta"))


def scan_session(path: Path) -> dict:
    prompts, hints, spawns, tools, results, models = [], [], [], [], {}, Counter()
    human = 0
    for d in read_jsonl(path):
        t = d.get("timestamp")
        msg = d.get("message") or {}
        att = d.get("attachment") or {}
        if att.get("type") == "hook_additional_context" and t:
            m = HINT_RE.search(" ".join(c for c in att.get("content", []) if isinstance(c, str)))
            if m:
                hints.append({"ts": ts(t), "provider": m.group(1), "confidence": float(m.group(2)), "tier": m.group(3)})
        if starts_turn(d) and t:
            prompts.append(ts(t))
            human += is_human(d)
        if d.get("type") == "assistant" and msg.get("model"):
            models[msg["model"]] += 1
        for c in msg.get("content") if isinstance(msg.get("content"), list) else []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and c.get("name") == "Agent" and t:
                spawns.append({"id": c.get("id"), "ts": ts(t), "model": (c.get("input") or {}).get("model")})
            elif c.get("type") == "tool_use" and str(c.get("name", "")).startswith("mcp__system1__"):
                tools.append({"id": c.get("id"), "name": c["name"].removeprefix("mcp__system1__")})
            elif c.get("type") == "tool_result" and c.get("tool_use_id"):
                results[c["tool_use_id"]] = c.get("content")
    main_model = models.most_common(1)[0][0] if models else None
    for tool in tools:
        text = results.get(tool["id"])
        if isinstance(text, list):
            text = " ".join(x.get("text", "") for x in text if isinstance(x, dict))
        m = re.search(r'"status":\s*"(\w+)"', text or "")
        tool["status"] = m.group(1) if m else None
    return {"prompts": sorted(prompts), "human_prompts": human, "hints": hints, "spawns": spawns, "tools": tools,
            "main_model": main_model}


def turn_of(t: float, prompts: list) -> int:
    """Index of the last prompt at or before t (-1 if none)."""
    i = -1
    for j, p in enumerate(prompts):
        if p <= t + 1:  # attachments can carry the same second as their prompt
            i = j
        else:
            break
    return i


def pct(n, d):
    return round(n / d, 3) if d else None


TIER_RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}


def shadow_stats(entries) -> dict:
    """Record-only Agent spawns from the routing log: System-1's tier against the orchestrator's choice.
    "inherit" (no model given) counts as opus, a lower bound since orchestrator sessions run opus or fable."""
    n = agree = cheaper = labeled = right = 0
    for e in entries:
        if e.get("source") != "agent" or not e.get("decision"):
            continue
        s1 = e["decision"].split(":", 1)[0]
        chosen = e.get("chosen") if e.get("chosen") in TIER_RANK else "opus"
        n += 1
        agree += s1 == chosen
        cheaper += TIER_RANK[s1] < TIER_RANK[chosen]
        if e.get("label") in TIER_RANK:
            labeled += 1
            right += s1 == e["label"]
    return {"spawns": n, "agree": pct(agree, n), "system1_cheaper": cheaper, "labeled": labeled,
            "accuracy_on_labeled": pct(right, labeled)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=float, default=14)
    ap.add_argument("--projects-dir", type=Path, default=Path("~/.claude/projects").expanduser())
    ap.add_argument("--prices", type=Path, default=Path(__file__).with_name("prices.json"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    prices = Prices(args.prices)
    since = time.time() - args.days * 86400

    reach = Counter()
    latencies, confidences, hint_tiers = [], [], Counter()
    tool_calls, decide_status = Counter(), Counter()
    outcome = Counter()  # followed / upgraded / downgraded / baseline
    projects_active = Counter()
    baseline_mix = Counter()
    per_tier_cost = defaultdict(lambda: [0, 0.0])  # tier -> [spawns, cost]
    followed_spawns, upgraded_spawns = [], []
    escalations = 0
    unpriced = Counter()
    overrides = []  # local prompt times (matching the routing log's "ts"), never text
    hint_overhead = 0.0

    scans = [(p, scan_session(p)) for p in args.projects_dir.glob("*/*.jsonl") if p.stat().st_mtime >= since]
    # Reach only counts sessions that started after the first hint anywhere, i.e. once routing was live.
    first_hint = min((h["ts"] for _, s in scans for h in s["hints"]), default=None)
    for path, s in scans:
        reach["sessions"] += 1
        reach["prompts"] += s["human_prompts"]
        active = bool(s["hints"] or s["tools"])
        if first_hint is not None and s["prompts"] and s["prompts"][0] >= first_hint - 3600:
            reach["sessions_since_routing"] += 1
            reach["active_since_routing"] += active
        if active:
            reach["active_sessions"] += 1
            reach["prompts_in_active_sessions"] += s["human_prompts"]
            projects_active[path.parent.name.rsplit("-", 1)[-1]] += 1
        main_tier = tier_of(s["main_model"], None)
        usage = subagent_usage(path.with_suffix(""))

        hint_by_turn = {}
        for h in s["hints"]:
            i = turn_of(h["ts"], s["prompts"])
            if i >= 0 and h["ts"] - s["prompts"][i] <= HINT_WINDOW_S:
                hint_by_turn[i] = h
                latencies.append(h["ts"] - s["prompts"][i])
            confidences.append(h["confidence"])
            hint_tiers[h["tier"]] += 1
        reach["hints"] += len(s["hints"])
        # Each hint is ~70 tokens of extra input for the main model (then cached); tiny, but it's the whole cost side.
        rates = prices.rates(s["main_model"] or "")
        if rates:
            hint_overhead += len(s["hints"]) * HINT_TOKENS * rates["input"] / 1e6
        for tool in s["tools"]:
            tool_calls[tool["name"]] += 1
            if tool["name"] == "system1_decide":
                decide_status[tool["status"] or "unknown"] += 1

        tiers_in_turn = defaultdict(list)
        for sp in s["spawns"]:
            tier = tier_of(sp["model"], main_tier)
            rows = usage.get(sp["id"], [])
            cost = 0.0
            for u, model in rows:
                c = prices.cost(u, model)
                if c is None:
                    unpriced[model] += 1
                else:
                    cost += c
            if tier:
                per_tier_cost[tier][0] += 1
                per_tier_cost[tier][1] += cost
            turn = turn_of(sp["ts"], s["prompts"])
            hint = hint_by_turn.get(turn)
            record = {"tier": tier, "cost": cost, "rows": rows, "hint": hint["tier"] if hint else None}
            if not hint or tier is None:
                outcome["baseline"] += 1
                if tier:
                    baseline_mix[tier] += 1
            elif tier == hint["tier"]:
                outcome["followed"] += 1
                followed_spawns.append(record)
            elif TIER_ORDER.index(tier) > TIER_ORDER.index(hint["tier"]):
                outcome["upgraded"] += 1
                upgraded_spawns.append(record)
                overrides.append({"prompt_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(s["prompts"][turn])),
                                  "hint": hint["tier"], "spawned": tier})
            else:
                outcome["downgraded"] += 1
                overrides.append({"prompt_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(s["prompts"][turn])),
                                  "hint": hint["tier"], "spawned": tier})
            # Proxy for rework: a hint-following spawn followed by a higher-tier spawn in the same turn.
            earlier = tiers_in_turn[turn]
            if hint and tier and any(e == hint["tier"] and TIER_ORDER.index(tier) > TIER_ORDER.index(e) for e in earlier):
                escalations += 1
            if tier:
                earlier.append(tier)

    def reprice(rows, tier):
        model = prices.tiers.get(tier)
        return sum(prices.cost(u, model) or 0.0 for u, _ in rows) if model else 0.0

    base_total = sum(baseline_mix.values())
    base_share = {t: n / base_total for t, n in baseline_mix.items()} if base_total else {}
    realised = sum(sum(share * reprice(r["rows"], t) for t, share in base_share.items()) - r["cost"]
                   for r in followed_spawns) if base_share else 0.0
    missed = sum(r["cost"] - reprice(r["rows"], r["hint"]) for r in upgraded_spawns)
    total_spawns = sum(outcome.values())
    hinted = outcome["followed"] + outcome["upgraded"] + outcome["downgraded"]

    try:
        cfg = load_config()
        log_file, log_dirs, routing_on = cfg.routing_log_file, cfg.routing_log_dirs, cfg.routing_enabled
    except ConfigError:
        log_file, log_dirs, routing_on = "", [], False
    log_path = Path(log_file).expanduser() if log_file else None
    log_entries = list(read_jsonl(log_path)) if log_path and log_path.is_file() else []
    log_total = len(log_entries)
    pending = unlabeled_count(log_file) if log_file else 0
    cal = [{k: e.get(k) for k in ("question", "n_options", "n_samples", "accuracy", "fitted_at", "data",
                                  "recommended_threshold")} for e in calibration.load()]

    report = {
        "window_days": args.days,
        "reach": {**reach, "hint_rate": pct(reach["hints"], reach["prompts_in_active_sessions"]),
                  "active_projects": dict(projects_active), "routing_enabled": routing_on},
        "hints": {"by_tier": dict(hint_tiers),
                  "mean_confidence": round(statistics.mean(confidences), 3) if confidences else None,
                  "hook_latency_s": {"median": round(statistics.median(latencies), 2) if latencies else None,
                                     "p90": round(sorted(latencies)[int(0.9 * (len(latencies) - 1))], 2)
                                     if latencies else None}},
        "mcp_tools": {"calls": dict(tool_calls), "decide_status": dict(decide_status)},
        "spawns": {"total": total_spawns, "in_hinted_turns": hinted, "outcomes": dict(outcome),
                   "adherence": pct(outcome["followed"], hinted), "baseline_mix": dict(baseline_mix),
                   "possible_escalations": escalations, "overrides": overrides},
        "cost_usd": {"by_tier": {t: {"spawns": n, "cost": round(c, 2)} for t, (n, c) in per_tier_cost.items()},
                     "total_subagents": round(sum(c for _, c in per_tier_cost.values()), 2),
                     "realised_savings": round(realised, 2), "missed_savings": round(missed, 2),
                     "hint_overhead": round(hint_overhead, 4),
                     "net_realised": round(realised - hint_overhead, 2),
                     "unpriced_models": dict(unpriced)},
        "overhead": {"hook_seconds_total": round(sum(latencies), 1)},
        "calibration": {"routing_log_entries": log_total, "unlabeled": pending, "log_dirs": len(log_dirs),
                        "shadow": shadow_stats(log_entries),
                        "entries": cal,
                        "seed_only": bool(cal) and all(str(e.get("data", "")).endswith("-seed.jsonl") for e in cal)},
    }
    flags = []
    if not routing_on:
        flags.append("routing_disabled")
    if reach["sessions_since_routing"] >= 3 and reach["active_since_routing"] / reach["sessions_since_routing"] < 0.5:
        flags.append("low_reach")
    if hinted >= 5 and (report["spawns"]["adherence"] or 0) < 0.5:
        flags.append("low_adherence")
    if outcome["upgraded"] > max(outcome["downgraded"], 0) and outcome["upgraded"] >= 3:
        flags.append("overrides_mostly_upgrade")
    if report["reach"]["hint_rate"] is not None and report["reach"]["hint_rate"] < 0.3:
        flags.append("mostly_abstaining")
    if (report["hints"]["hook_latency_s"]["median"] or 0) > 1.0:
        flags.append("slow_hook")
    if report["calibration"]["seed_only"]:
        flags.append("seed_only_calibration")
    if pending >= CALIBRATE_EVERY:
        flags.append("labels_pending")
    if escalations:
        flags.append("possible_rework")
    if hinted < 10:
        flags.append("too_little_data")
    report["flags"] = flags

    if args.json:
        print(json.dumps(report, indent=2))
        return
    r, sp, c = report["reach"], report["spawns"], report["cost_usd"]
    print(f"System-1 usage, last {args.days:g} days")
    print(f"  reach: {r.get('active_since_routing', 0)}/{r.get('sessions_since_routing', 0)} sessions active since routing "
          f"went live ({r.get('active_sessions', 0)}/{r.get('sessions', 0)} in the window); "
          f"{r.get('hints', 0)} hints over {r.get('prompts_in_active_sessions', 0)} prompts (rate {r['hint_rate']})")
    print(f"  hints by tier {report['hints']['by_tier']}, mean confidence {report['hints']['mean_confidence']}, "
          f"hook latency median {report['hints']['hook_latency_s']['median']} s")
    print(f"  MCP tools {report['mcp_tools']['calls']}, decide outcomes {report['mcp_tools']['decide_status']}")
    print(f"  spawns: {sp['total']} total, {sp['in_hinted_turns']} after a hint -> {sp['outcomes']}, "
          f"adherence {sp['adherence']}")
    print(f"  baseline mix (no hint): {sp['baseline_mix']}")
    print(f"  subagent cost ${c['total_subagents']}: {c['by_tier']}")
    print(f"  savings: realised ${c['realised_savings']} (net of hint tokens ${c['net_realised']}), "
          f"missed (upgraded past a hint) ${c['missed_savings']}; hook time {report['overhead']['hook_seconds_total']} s")
    cal_line = report["calibration"]
    print(f"  calibration: {len(cal_line['entries'])} fits{' (seed data only)' if cal_line['seed_only'] else ''}; "
          f"routing log {cal_line['routing_log_entries']} entries, {cal_line['unlabeled']} unlabeled")
    sh = cal_line["shadow"]
    print(f"  shadow (record-only spawns): {sh['spawns']}, System-1 agrees {sh['agree']}, would pick cheaper "
          f"{sh['system1_cheaper']}, right on {sh['accuracy_on_labeled']} of {sh['labeled']} labeled")
    print(f"  flags: {', '.join(flags) or 'none'}")


if __name__ == "__main__":
    main()
