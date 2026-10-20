"""A loopback POST /v1/systemone server for decision engines that ship only as Hugging Face weights, so the
gateway's `systemone` provider can call them over HTTP like Von or llama-server. Optional: run it in its own
venv with the engine's packages (torch, transformers, sentence-transformers; plus anyjev or openthai-systemone).

    python engines/systemone/serve.py --engine gte            # Alibaba-NLP/gte-reranker-modernbert-base
    python engines/systemone/serve.py --engine qwen3-rerank   # Qwen/Qwen3-Reranker-0.6B
    python engines/systemone/serve.py --engine anyjev         # AnyJev L0 over Qwen/Qwen3-1.7B (4-bit)
    python engines/systemone/serve.py --engine openthai       # iapp/OpenThai-SystemOne

`--model` overrides the Hugging Face id, `--port` the port (8790). Liquid AI's d1 models need no script:
llama.cpp's `llama-server -m d1-3B-Q8_0.gguf` answers /v1/systemone itself. Only `choice` questions are
answered (what the provider sends); the scoring is the naga bench's (bench/naga/eng_*.py). It binds 127.0.0.1
only, refuses any Host header but 127.0.0.1/localhost on its port, bodies that are not JSON or over 1 MB, and
more than 16 questions or 256 options; set SYSTEM1_SYSTEMONE_API_KEY (in both the server's and the gateway's
environment) to also require that bearer token. It is for one machine only.
"""

import argparse
import hmac
import json
import math
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

MAX_BODY = 1_000_000           # bytes
MAX_QUESTIONS, MAX_OPTIONS = 16, 256
TOKEN_ENV = "SYSTEM1_SYSTEMONE_API_KEY"  # the same variable the gateway's systemone provider sends as a bearer token
DEFAULTS = {"gte": "Alibaba-NLP/gte-reranker-modernbert-base", "qwen3-rerank": "Qwen/Qwen3-Reranker-0.6B",
            "anyjev": "Qwen/Qwen3-1.7B", "openthai": "iapp/OpenThai-SystemOne"}


def softmax(scores: dict) -> dict:
    m = max(scores.values())
    e = {k: math.exp(v - m) for k, v in scores.items()}
    total = sum(e.values())
    return {k: v / total for k, v in e.items()}


def label_text(name, description):
    return f"{name}: {description}" if description and description != name else name


def load(engine: str, model: str):
    """Return choose(state, instructions, criteria) -> {option: probability}. Imports stay here: the module
    itself is stdlib, so the tests can drive the server with a fake chooser."""
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if engine == "gte":
        from sentence_transformers import CrossEncoder
        m = CrossEncoder(model, device=dev)

        def choose(state, instructions, criteria):
            names = list(criteria)
            s = m.predict([(state, label_text(n, criteria[n])) for n in names], activation_fn=torch.nn.Identity())
            return softmax(dict(zip(names, map(float, s))))
        return choose
    if engine == "qwen3-rerank":
        from transformers import AutoModelForCausalLM, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(model, padding_side="left")
        lm = AutoModelForCausalLM.from_pretrained(model, dtype=torch.float16 if dev == "cuda" else torch.float32).to(dev).eval()
        yes, no = tok.convert_tokens_to_ids("yes"), tok.convert_tokens_to_ids("no")
        head = ("<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the "
                "Instruct provided. Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n")
        tail = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

        @torch.no_grad()
        def choose(state, instructions, criteria):
            names = list(criteria)
            texts = [f"{head}<Instruct>: {instructions}\n<Query>: {state}\n<Document>: {label_text(n, criteria[n])}{tail}"
                     for n in names]
            enc = tok(texts, padding=True, return_tensors="pt").to(dev)
            last = lm(**enc).logits[:, -1, :]
            s = torch.log_softmax(torch.stack([last[:, no], last[:, yes]], 1).float(), 1)[:, 1].tolist()
            return softmax(dict(zip(names, s)))
        return choose
    if engine == "anyjev":
        from anyjev import Decider, Question
        from anyjev.backends.hf import HFBackend
        from transformers import BitsAndBytesConfig
        q4 = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)
        d = Decider(HFBackend(model, dtype="float16", batch_size=2, quantization_config=q4), level="L0", max_permutations=2)

        def choose(state, instructions, criteria):
            texts = {label_text(n, criteria[n]): n for n in criteria}
            dist = d.decide(state, [Question.choice(instructions, list(texts), name="q")])[0].distribution
            return {texts[t]: p for t, p in dist.items()}
        return choose
    if engine == "openthai":
        from openthai_systemone import SystemOneClient
        client = SystemOneClient(model, device=dev, dtype=torch.float16 if dev == "cuda" else None)

        def choose(state, instructions, criteria):
            q = {"type": "choice", "instructions": instructions, "criteria": criteria}
            return dict(client.system_one(state, {"q": q}).answers["q"].probabilities)
        return choose
    raise ValueError(engine)


def make_handler(choose, engine: str, token: str = ""):
    class Handler(BaseHTTPRequestHandler):
        def _refused(self):
            """Why this request must not reach the model, or None. A browser page can reach 127.0.0.1 too: the Host
            check stops DNS rebinding, the JSON content type stops a plain form post, the caps stop a huge body."""
            port = self.server.server_port
            if self.headers.get("Host", "") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                return 403, "Host must be 127.0.0.1 or localhost with this port"
            if token and not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}"):
                return 401, "missing or wrong bearer token"
            return None

        def _send(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            refused = self._refused()
            if refused:
                return self._send({"detail": refused[1]}, refused[0])
            if self.path == "/health":
                return self._send({"status": "ok", "engine": engine})
            self._send({"detail": "not found"}, 404)

        def do_POST(self):
            refused = self._refused()
            if refused:
                return self._send({"detail": refused[1]}, refused[0])
            if self.path != "/v1/systemone":
                return self._send({"detail": "not found"}, 404)
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return self._send({"detail": "Content-Type must be application/json"}, 415)
            length = self.headers.get("Content-Length", "")
            if not length.isdigit() or not 0 < int(length) <= MAX_BODY:
                return self._send({"detail": f"Content-Length must be 1..{MAX_BODY}"}, 413)
            try:
                body = json.loads(self.rfile.read(int(length)))
                if len(body["questions"]) > MAX_QUESTIONS or any(len(q.get("criteria") or ()) > MAX_OPTIONS
                                                                 for q in body["questions"].values()):
                    return self._send({"detail": f"at most {MAX_QUESTIONS} questions of {MAX_OPTIONS} options"}, 422)
                state = body.get("state")
                state = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)
                answers = {}
                for key, q in body["questions"].items():
                    if q.get("type") != "choice" or not isinstance(q.get("criteria"), dict) or len(q["criteria"]) < 2:
                        return self._send({"detail": f"{key}: only choice questions with 2+ criteria"}, 422)
                    probs = choose(state, str(q.get("instructions", "")), q["criteria"])
                    best = max(probs, key=probs.get)
                    answers[key] = {"type": "choice", "choice": best, "probabilities": probs, "confidence": probs[best]}
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                return self._send({"detail": f"bad request: {e}"}, 400)
            self._send({"model": engine, "answers": answers})

        def log_message(self, *a):
            pass
    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--engine", required=True, choices=sorted(DEFAULTS))
    ap.add_argument("--model", default="")
    ap.add_argument("--port", type=int, default=8790)
    a = ap.parse_args()
    server = HTTPServer(  # one request at a time: one model on one GPU
        ("127.0.0.1", a.port), make_handler(load(a.engine, a.model or DEFAULTS[a.engine]), a.engine,
                                            os.environ.get(TOKEN_ENV, "")))
    print(f"{a.engine} on http://127.0.0.1:{a.port}/v1/systemone", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
