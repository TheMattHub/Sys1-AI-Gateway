"""iapp/OpenThai-SystemOne (0.8B, Apache-2.0, Qwen3.5-0.8B base with a 256-slot decision head):
`python eng_openthai.py openthai|openthai-ollama`.

openthai         the Hugging Face weights through the model's own client (`pip install openthai-systemone==0.1.0`,
                 bench venv, float16 on the GPU): one `choice` question, criteria {label: document}, up to 255
                 options, so every task goes as it is (the client averages option orders above 10 options).
openthai-ollama  its Ollama build `iapp/openthai-systemone:0.8b` (Q8_0) through the gateway's ollama provider
                 (POST /api/chat, letter logprobs), asked as Gemma is: at most 26 letters, label sets above 20 get
                 the harrier top 20 (eng_gateway.prepare). Ollama 0.40.6's own POST /v1/systemone refuses this
                 build ("not a llama.cpp decision model"), and the build was fine-tuned for that prompt, not ours."""
import sys

import common
from eng_gateway import OllamaProvider, prepare, via_provider


def native():
    import torch
    from openthai_systemone import SystemOneClient
    client = SystemOneClient("iapp/OpenThai-SystemOne", device="cuda", dtype=torch.float16)

    def decide(it):
        q = {"type": "choice", "instructions": common.question(it), "criteria": {o: it["docs"][o] for o in it["options"]}}
        probs = client.system_one(it["text"], {"decision": q}).answers["decision"].probabilities
        order = sorted(probs, key=lambda k: -probs[k])
        return {"ranking": order, "confidence": probs[order[0]]}
    return decide


if __name__ == "__main__":
    name = sys.argv[1]
    if name == "openthai":
        common.run(name, native())
    else:
        common.run(name, via_provider(OllamaProvider({"model": "iapp/openthai-systemone:0.8b"})), prepare=prepare)
