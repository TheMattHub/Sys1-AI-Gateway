"""AnyJev (Nokia, Apache-2.0, `pip install anyjev==0.3.0`), the training-free decision layer, over Qwen3-1.7B
(Apache-2.0) in 4-bit (bitsandbytes NF4: its bfloat16 weights, 4.1 GB, do not fit the 4 GB GPU):
`python eng_anyjev.py` in the bench venv. One model per process.

The Decider at level L0 with two rotations of the options (the settings of AnyJev's Decision Index entry):
the letter readout is read once per rotation, the position bias averaged out and the label prior divided out,
with no labels. Options are shown as "label: document"; AnyJev reads letters, so at most 26 options:
T's 10 candidates go as they are, longer label sets (all 90 tools, the 31 distributions) get the harrier top
20 as Laya and Gemma do (eng_gateway.prepare)."""
import torch

import common
from eng_gateway import CAP, _short, prepare

MODEL = "Qwen/Qwen3-1.7B"


def make():
    from anyjev import Decider, Question
    from anyjev.backends.hf import HFBackend
    from transformers import BitsAndBytesConfig
    q4 = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)
    backend = HFBackend(MODEL, dtype="float16", batch_size=2, quantization_config=q4)
    d = Decider(backend, level="L0", max_permutations=2)

    def decide(it):
        opts = _short.get((it["task"], it["id"]), it["options"])[:CAP] if len(it["options"]) > 26 else it["options"]
        texts = [it["docs"][o] if it["docs"][o].startswith(o) else f"{o}: {it['docs'][o]}" for o in opts]
        r = d.decide(it["text"], [Question.choice(common.question(it), texts, name="decision")])
        dist = r[0].distribution if hasattr(r, "__getitem__") else r.items[0].distribution
        back = dict(zip(texts, opts))
        order = sorted(dist, key=lambda t: -dist[t])
        return {"ranking": [back[t] for t in order], "confidence": dist[order[0]]}
    return decide


if __name__ == "__main__":
    common.run("anyjev", make(), prepare=prepare)
