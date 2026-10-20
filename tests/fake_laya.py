"""Local stand-in for `laya-serve`, speaking its real wire format (see system1_gateway/providers/laya.py).

Choice questions: probabilities follow word overlap between the state/instructions and each option
(uniform when nothing overlaps, which makes the gateway abstain). Yes/no (noul) questions: p(yes) = 0.9.
Magic instructions for tests: __fail__ -> HTTP 500, __garbage__ -> non-JSON body, __slow__ -> 2 s delay.
Tests may set Handler.canned (a response dict to return verbatim); Handler.requests records each request.

    python tests/fake_laya.py --port 8765
"""

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _words(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def answer(question: dict, state: dict) -> dict:
    if question.get("type") == "noul":
        return {"type": "noul", "noul": 0.9, "confidence": 0.9, "answer_confidence": 0.9}
    options = question["criteria"]
    signal = _words(question.get("instructions", "") + " " + json.dumps(state))
    weights = {o: len(_words(o) & signal) for o in options}
    total = sum(weights.values())
    probs = {o: round(w / total if total else 1 / len(options), 4) for o, w in weights.items()}
    best = max(options, key=probs.get)
    return {"type": "choice", "choice": best, "probabilities": probs,
            "confidence": 0.0, "answer_confidence": probs[best]}


class Handler(BaseHTTPRequestHandler):
    canned = None
    requests = []

    def _send(self, code: int, body: bytes, content_type="application/json"):
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except ConnectionError:
            pass  # the client already gave up (timeout tests)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, b'{"status": "ok", "loaded": ["typed-decisions"], "device": "cpu"}')
        self._send(404, b'{"detail": "Not Found"}')

    def do_POST(self):
        if self.path != "/v1/systemone":
            return self._send(404, b'{"detail": "Not Found"}')
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        Handler.requests.append({"body": body, "authorization": self.headers.get("Authorization")})
        if Handler.canned is not None:
            return self._send(200, json.dumps(Handler.canned).encode("utf-8"))
        questions = body.get("questions", {})
        instructions = " ".join(q.get("instructions", "") for q in questions.values())
        if "__fail__" in instructions:
            return self._send(500, b'{"detail": "boom"}')
        if "__garbage__" in instructions:
            return self._send(200, b"<html>not json</html>", "text/html")
        if "__slow__" in instructions:
            time.sleep(2)
        model = body.get("model") or "english"
        result = {"model": "laya-rl-agent",
                  "answers": {name: answer(q, body.get("state") or {}) for name, q in questions.items()},
                  "routing": {"model": model, "repo": f"convaiinnovations/laya/{model}", "reason": "fake"}}
        self._send(200, json.dumps(result).encode("utf-8"))

    def log_message(self, *args):
        pass


def start(host="127.0.0.1", port=0) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    port = parser.parse_args().port
    print(f"fake Laya listening on http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
