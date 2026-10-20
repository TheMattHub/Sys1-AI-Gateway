"""Hugging Face encoders in the bench venv: `python eng_hf.py <engine> [model_path]`.

harrier-bi    microsoft/harrier-oss-v1-270m bi-encoder (cosine; confidence = top-1 minus top-2 cosine)
gte-rerank    Alibaba-NLP/gte-reranker-modernbert-base cross-encoder (confidence = softmax over options)
qwen3-rerank  Qwen/Qwen3-Reranker-0.6B, the model card's yes/no prompt (confidence = softmax of yes-logits)
nli           tasksource/ModernBERT-large-nli zero-shot-classification (label docs as candidate labels)
tuned         a cross-encoder fine-tuned by tune.py (model_path given)
T re-ranks find_tool's 10 candidates; B ranks every label. One model per process (4 GB GPU)."""
import sys

import torch

import common

torch.manual_seed(0)
DEV = "cuda" if torch.cuda.is_available() else "cpu"


def bi():
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer("microsoft/harrier-oss-v1-270m", device=DEV)
    cache = {}

    def decide(it):
        docs = [it["docs"][o] for o in it["options"]]
        key = tuple(docs)
        if key not in cache:
            cache[key] = m.encode_document(docs, convert_to_tensor=True, normalize_embeddings=True)
        q = m.encode_query([f"{common.question(it)} {it['text']}"], convert_to_tensor=True, normalize_embeddings=True)
        s = (q @ cache[key].T)[0].tolist()
        return _ranked(it, s, margin=True)
    return decide


def _ranked(it, scores, margin=False):
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    top = sorted(scores, reverse=True)
    conf = (top[0] - top[1] if len(top) > 1 else 1.0) if margin else common.softmax_top(scores)
    return {"ranking": [it["options"][i] for i in order], "confidence": conf}


def cross(model_id):
    from sentence_transformers import CrossEncoder
    m = CrossEncoder(model_id, device=DEV, model_kwargs={"torch_dtype": torch.float16} if DEV == "cuda" else {})

    def decide(it):
        s = m.predict([(it["text"], it["docs"][o]) for o in it["options"]], batch_size=32, activation_fn=torch.nn.Identity())
        return _ranked(it, [float(x) for x in s])
    return decide


def qwen3():
    # The model card's own usage (AutoModelForCausalLM, "yes"/"no" logits of the last token).
    from transformers import AutoModelForCausalLM, AutoTokenizer
    mid = "Qwen/Qwen3-Reranker-0.6B"
    tok = AutoTokenizer.from_pretrained(mid, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(mid, torch_dtype=torch.float16).to(DEV).eval()
    yes, no = tok.convert_tokens_to_ids("yes"), tok.convert_tokens_to_ids("no")
    prefix = ("<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the "
              "Instruct provided. Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n")
    suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    instruct = {"T": "Given a request to a simulation engine's assistant, find the tool that does it",
                "blocks": "Given a modeller's sentence, find the simulation block type that models it",
                "distributions": "Given a description of a quantity, find the probability distribution that fits it",
                "fields": "Given a key or phrase, find the record field it means"}

    @torch.no_grad()
    def decide(it):
        texts = [f"{prefix}<Instruct>: {instruct[common.kind(it)]}\n<Query>: {it['text']}\n<Document>: {it['docs'][o]}{suffix}"
                 for o in it["options"]]
        scores = []
        for i in range(0, len(texts), 8):
            enc = tok(texts[i:i + 8], padding=True, return_tensors="pt").to(DEV)
            last = model(**enc).logits[:, -1, :]
            scores += torch.log_softmax(torch.stack([last[:, no], last[:, yes]], 1).float(), 1)[:, 1].tolist()
        return _ranked(it, scores)
    return decide


def nli():
    from transformers import pipeline
    clf = pipeline("zero-shot-classification", model="tasksource/ModernBERT-large-nli", device=0 if DEV == "cuda" else -1)

    def decide(it):
        docs = [it["docs"][o] for o in it["options"]]
        out = clf(it["text"], candidate_labels=docs)
        back = {it["docs"][o]: o for o in it["options"]}
        return {"ranking": [back[l] for l in out["labels"]], "confidence": out["scores"][0]}
    return decide


def gliner():
    # Native form: a classification task with {label: description}; multi_label with softmax and top_k = all
    # returns every label's probability, so top-3 can be read.
    from gliner2 import GLiNER2
    m = GLiNER2.from_pretrained("fastino/GLiNER2.5-Decide")
    m.to(DEV)

    short = {}
    if common.R2:     # 90 long tool documents run the 4 GB GPU out of memory: Tall gets the harrier top 20 (as Laya)
        import json
        short = {r["id"]: r["ranking"][:20] for r in map(json.loads, (common.RESULTS / "harrier-bi.Tall.jsonl").read_text(encoding="utf-8").splitlines())}

    def decide(it):
        opts = short[it["id"]] if it["task"] == "Tall" else it["options"]
        task = {"labels": {o: it["docs"][o] for o in opts}, "multi_label": True, "class_act": "softmax",
                "cls_threshold": 0.0, "top_k": len(opts), "prompt": common.question(it)}
        out = m.classify_text(it["text"], {"choice": task}, include_confidence=True)["choice"]
        pairs = [(d["label"], d["confidence"]) if isinstance(d, dict) else tuple(d) for d in out]
        pairs.sort(key=lambda p: -p[1])
        return {"ranking": [p[0] for p in pairs], "confidence": pairs[0][1]}
    return decide


if __name__ == "__main__":
    name = sys.argv[1]
    make = {"harrier-bi": bi, "gte-rerank": lambda: cross("Alibaba-NLP/gte-reranker-modernbert-base"),
            "qwen3-rerank": qwen3, "nli": nli, "gliner2": gliner, "tuned": lambda: cross(sys.argv[2])}[name]
    common.run(name, make())
