"""Phase 3: retries after a wrong pick, plain vs nudged (bench venv): `python retry.py tuned|laya`.

A pick is wrong when it is not in the item's gold. Up to 3 attempts; each retry removes the rejected labels from
the options. Nudged: the request also says what each rejected label does (its one-line summary), never the
answer. tuned: query becomes "<request> (not: s1; s2)"; laya: the same text in its `context` field.
Laya's shortlist (cap 20) is refilled from the harrier ranking after each removal; harrier's recorded latency
is added once per request when a shortlist was needed. Output: results2/retry.<engine>.<variant>.<task>.jsonl."""
import json
import sys
import time
import uuid

import common
import eng_gateway

TASKS = ("T", "Tall", "blocks", "distributions")


def harrier(task):
    rows = [json.loads(x) for x in (common.RESULTS / f"harrier-bi.{task}.jsonl").read_text(encoding="utf-8").splitlines() if x]
    return {r["id"]: r for r in rows}


def tuned_ranker():
    import tune
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    path = str(common.HERE / "models" / "tuned2")
    tok = AutoTokenizer.from_pretrained(path)
    model = AutoModelForSequenceClassification.from_pretrained(path).to("cuda").eval()
    score = tune.scorer(tok, model)

    def rank(it, opts, nudge):
        q = it["text"] + (f" (not: {nudge})" if nudge else "")
        s = score(q, [it["docs"][o] for o in opts])
        return [opts[i] for i in sorted(range(len(s)), key=lambda i: -s[i])]
    return rank


def laya_ranker():
    from system1_gateway.providers.laya import LayaProvider
    from system1_gateway.schema import DecideRequest
    prov = LayaProvider({"model": "typed-decisions"})

    def rank(it, opts, nudge):
        back = {it["docs"][o]: o for o in opts}
        ctx = {"task": it["text"], **({"not": nudge} if nudge else {})}
        ans = prov.decide(DecideRequest(question=common.question(it), request_id=uuid.uuid4().hex,
                                        options=list(back), context=ctx), eng_gateway.TIMEOUT)
        p = ans["probabilities"]
        return [back[k] for k in sorted(p, key=lambda k: -p[k])]
    return rank


def attempt_loop(it, rank, nudged, order):
    """order: the full preference list the options come from (all options; for laya the harrier order)."""
    rejected, spent = [], 0.0
    for a in (1, 2, 3):
        pool = [o for o in order if o not in rejected]
        opts = pool[:eng_gateway.CAP] if rank.cap else pool
        note = "; ".join(f"{r}: {it['summaries'][r]}" for r in rejected) if nudged and rejected else ""
        t0 = time.perf_counter()
        pick = rank(it, opts, note)[0]
        spent += time.perf_counter() - t0
        if pick in it["gold"]:
            return a, spent, rejected
        rejected.append(pick)
    return None, spent, rejected


def main(engine):
    rank = {"tuned": tuned_ranker, "laya": laya_ranker}[engine]()
    rank.cap = engine == "laya"
    for task in TASKS:
        h = harrier(task) if engine == "laya" else None
        its = common.items(task)
        for variant in ("plain", "nudged"):
            rows = []
            for it in its:
                order, extra = it["options"], 0.0
                if h and len(it["options"]) > eng_gateway.CAP:
                    order, extra = h[it["id"]]["ranking"], h[it["id"]]["latency_s"]
                won, spent, rej = attempt_loop(it, rank, variant == "nudged", order)
                rows.append({"id": it["id"], "split": it["split"], "won_at": won, "time_s": spent + extra, "rejected": rej})
            (common.RESULTS / f"retry.{engine}.{variant}.{task}.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            print(engine, task, variant, [sum(r["won_at"] is not None and r["won_at"] <= k for r in rows) for k in (1, 2, 3)],
                  f"of {len(rows)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
