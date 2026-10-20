"""Phase 4: fewer choices for tool selection, T mode "all" (bench venv): `python phase4.py tuned|gte|laya` then
`python phase4.py report`. Families and merge groups come from data/families.json (written before any run).
4a context subset (study open = the gold tool starts with study_), 4b two-stage family then tool, 4c merged
near-duplicates as an upper bound on 4b (a pick in a group of the gold tool counts as right).
Laya takes at most 20 options: a larger set is cut to the harrier ranking's top 20 inside that set."""
import json
import sys
import uuid

import common
import eng_gateway

FAM = json.loads((common.DATA / "families.json").read_text(encoding="utf-8"))
TOOLS = json.loads((common.DERIVED / "tools.json").read_text(encoding="utf-8"))
FAM_OF = {t: f for f, v in FAM["families"].items() for t in v["tools"]}
READ = set(FAM["study_open_extra_read_only"])
FAM_DOCS = {f: f"{f}: {v['description']} Tools: " + "; ".join(f"{t}: {TOOLS[t]['summary'][:90]}" for t in v["tools"])
            for f, v in FAM["families"].items()}


def ranker(engine):
    if engine == "laya":
        from system1_gateway.providers.laya import LayaProvider
        from system1_gateway.schema import DecideRequest
        prov = LayaProvider({"model": "typed-decisions"})

        def rank(q, docs, order, question):
            opts = order[:eng_gateway.CAP]
            back = {docs[o]: o for o in opts}
            ans = prov.decide(DecideRequest(question=question, request_id=uuid.uuid4().hex, options=list(back),
                                            context={"task": q}), eng_gateway.TIMEOUT)
            p = ans["probabilities"]
            return [back[k] for k in sorted(p, key=lambda k: -p[k])]
        return rank
    if engine == "tuned":
        import tune
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        path = str(common.HERE / "models" / "tuned2")
        score = tune.scorer(AutoTokenizer.from_pretrained(path), AutoModelForSequenceClassification.from_pretrained(path).to("cuda").eval())
    else:
        import torch
        from sentence_transformers import CrossEncoder
        m = CrossEncoder("Alibaba-NLP/gte-reranker-modernbert-base", device="cuda", model_kwargs={"torch_dtype": torch.float16})
        score = lambda q, ds: [float(x) for x in m.predict([(q, d) for d in ds], batch_size=32, activation_fn=torch.nn.Identity())]

    def rank(q, docs, order, question):
        s = score(q, [docs[o] for o in order])
        return [order[i] for i in sorted(range(len(s)), key=lambda i: -s[i])]
    return rank


def run(engine):
    rank = ranker(engine)
    harrier = {r["id"]: r["ranking"] for r in map(json.loads, (common.RESULTS / "harrier-bi.Tall.jsonl").read_text(encoding="utf-8").splitlines()) }
    docs = {t: v["doc"] for t, v in TOOLS.items()}
    rows = []
    for it in common.items("Tall"):
        gold, h = it["gold"], harrier[it["id"]]
        order_of = lambda s: [t for t in (h if engine == "laya" else list(TOOLS)) if t in s]
        # 4a
        study = any(g.startswith("study_") for g in gold)
        offered = {t for t in TOOLS if (t.startswith("study_") or t in READ)} if study else {t for t in TOOLS if not t.startswith("study_")}
        ra = rank(it["text"], docs, order_of(offered), common.question(it))
        # 4b
        fams = list(FAM["families"])
        rf = rank(it["text"], FAM_DOCS, fams, "Which family of tools should the assistant use for this request?")
        pred = rf[0]
        rt = rank(it["text"], docs, order_of(set(FAM["families"][pred]["tools"])), common.question(it))
        true_fams = {FAM_OF[g] for g in gold}
        rt_true = rank(it["text"], docs, order_of(set(FAM["families"][sorted(true_fams)[0]]["tools"])), common.question(it))
        rows.append({"id": it["id"], "split": it["split"], "gold": gold, "study": study, "offered_has_gold": any(g in offered for g in gold),
                     "a": ra[:3], "fam_rank": rf[:3], "true_fams": sorted(true_fams), "b": rt[:3], "b_true": rt_true[:3]})
        print(engine, it["id"], flush=True) if len(rows) % 20 == 0 else None
    (common.RESULTS / f"phase4.{engine}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def report():
    groups = FAM["merge_groups"]
    out = ["Study open = the gold tool starts with study_. Cells are TEST / TRAIN counts (25 / 54 rows). End-to-end top-3 = a gold tool in the "
           "first three of the stage-2 ranking inside the stage-1 top-1 family. Baseline = single-stage over all 90 (round-2 Tall run).\n",
           "| engine | single-stage 90: top-1 / top-3 | 4a subset: top-1 / top-3 (gold offered) | 4b stage 1 family top-1 | 4b stage 2 given true family top-1 | 4b end-to-end top-1 / top-3 | 4c group-right top-1 (gain) |\n|---|---|---|---|---|---|---|"]
    gains_all = {}
    for e in ("tuned", "gte", "laya"):
        p = common.RESULTS / f"phase4.{e}.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]
        base_name = {"tuned": "tuned", "gte": "gte-rerank", "laya": "laya"}[e]
        base = {json.loads(x)["id"]: json.loads(x) for x in (common.RESULTS / f"{base_name}.Tall.jsonl").read_text(encoding="utf-8").splitlines()}
        cells = []
        for split in ("TEST", "TRAIN"):
            rs = [r for r in rows if r["split"] == split]
            g = lambda rk, k, r: any(x in r["gold"] for x in rk[:k])
            one = lambda f: sum(f(r) for r in rs)
            s1 = one(lambda r: g(base[r["id"]]["ranking"], 1, r)), one(lambda r: g(base[r["id"]]["ranking"], 3, r))
            a1, a3, off = one(lambda r: g(r["a"], 1, r)), one(lambda r: g(r["a"], 3, r)), one(lambda r: r["offered_has_gold"])
            f1 = one(lambda r: r["fam_rank"][0] in r["true_fams"])
            st2 = one(lambda r: g(r["b_true"], 1, r))
            e1, e3 = one(lambda r: g(r["b"], 1, r)), one(lambda r: g(r["b"], 3, r))

            def grp(r):
                ok = set(r["gold"])
                for name, ts in groups.items():
                    if ok & set(ts):
                        ok |= set(ts)
                return r["b"][0] in ok
            gr = one(grp)
            for r in rs:
                if not g(r["b"], 1, r) and grp(r):
                    for name, ts in groups.items():
                        if set(r["gold"]) & set(ts) and r["b"][0] in ts:
                            gains_all.setdefault(split, {}).setdefault(name, []).append(f"{e}:{r['id']}")
            cells.append((s1, a1, a3, off, f1, st2, e1, e3, gr, len(rs)))
        te, tr = cells
        j = lambda i: f"{te[i]} / {tr[i]}"
        out.append(f"| {e} | {te[0][0]}/{te[0][1]} / {tr[0][0]}/{tr[0][1]} | {te[1]}/{te[2]} / {tr[1]}/{tr[2]} ({te[3]}/{te[9]} / {tr[3]}/{tr[9]}) | {j(4)} | {j(5)} "
                   f"| {te[6]}/{te[7]} / {tr[6]}/{tr[7]} | {j(8)} (+{te[8]-te[6]} / +{tr[8]-tr[6]}) |")
    out.append("\nGroups that gave 4c gains (engine:row):")
    for split, d in gains_all.items():
        out.append(f"- {split}: " + "; ".join(f"{k} ({', '.join(v)})" for k, v in d.items()))
    (common.HERE / "phase4.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    report() if sys.argv[1] == "report" else run(sys.argv[1])
