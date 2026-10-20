import json
import math
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from system1_gateway.config import Config
from system1_gateway.gateway import Gateway


class Fake(BaseHTTPRequestHandler):
    """Von and Ollama wire formats, enough for the adapters. `mode` switches Ollama's reply."""
    requests, mode = [], "letters"

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._send({"status": "ok", "engine": "von-1.3"})
        if self.path == "/api/tags":
            return self._send({"models": [{"name": "gemma4:e4b"}]})
        self._send({"detail": "nf"}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.requests.append((self.path, body))
        if self.path == "/v1/systemone":
            answers = {}
            for key, q in body["questions"].items():
                if not isinstance(q["criteria"], dict):
                    return self._send({"detail": "criteria should be a valid dictionary"}, 422)
                names = list(q["criteria"])
                probs = {n: (0.8 if i == 0 else 0.2 / (len(names) - 1)) for i, n in enumerate(names)}
                answers[key] = {"type": "choice", "choice": names[0], "probabilities": probs, "confidence": 0.5}
            return self._send({"model": "von-1.3.0", "answers": answers})
        if self.path == "/api/chat":
            if Fake.mode == "text":
                return self._send({"message": {"content": "I think A"}})
            if Fake.mode == "prose":  # ignores the one-letter format; letters keep a little residual mass
                top = [{"token": "I", "logprob": math.log(0.9)}, {"token": "A", "logprob": math.log(0.06)}]
                return self._send({"message": {"content": "I"}, "logprobs": [{"token": "I", "logprob": math.log(0.9),
                                                                              "top_logprobs": top}]})
            top = [{"token": "B", "logprob": math.log(0.6)}, {"token": " A", "logprob": math.log(0.3)},
                   {"token": "Z", "logprob": math.log(0.1)}]
            return self._send({"message": {"content": "B"}, "logprobs": [{"token": "B", "logprob": math.log(0.6),
                                                                          "top_logprobs": top}]})

    def log_message(self, *a):
        pass


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Fake.requests.clear()
        Fake.mode = "letters"

    def gw(self, name, **settings):
        return Gateway(Config(provider=name, min_confidence=0.0, providers={name: {"endpoint": self.url, **settings}}))

    def test_von_decide_and_batch(self):
        g = self.gw("von")
        r = g.decide({"question": "Tier?", "options": ["haiku: small", "opus: big"], "context": {"task": "x"}})
        self.assertEqual((r["status"], r["decision"], r["confidence"]), ("decided", "haiku: small", 0.8))
        q = Fake.requests[-1][1]["questions"]["decision"]
        self.assertEqual(q["criteria"], {"haiku: small": "haiku: small", "opus: big": "opus: big"})
        Fake.requests.clear()
        out = g.decide_many({"a": {"question": "A?", "options": ["yes", "no"], "context": {"task": "x"}},
                             "b": {"question": "B?", "options": ["yes", "no"], "context": {"task": "x"}}})
        self.assertEqual(len(Fake.requests), 1)
        self.assertEqual({r["decision"] for r in out.values()}, {"yes"})
        self.assertTrue(g.health()["providers"][0]["ok"])

    def test_ollama_letters(self):
        g = self.gw("ollama", model="gemma4:e4b")
        r = g.decide({"question": "Tier?", "options": ["haiku", "sonnet"], "context": {"task": "Rename x"}})
        self.assertEqual((r["status"], r["decision"]), ("decided", "sonnet"))
        self.assertAlmostEqual(r["confidence"], 0.6 / 0.9, places=3)  # Z isn't an option letter
        body = Fake.requests[-1][1]
        self.assertEqual(body["messages"][1]["content"], "Rename x")
        self.assertIn("A = haiku", body["messages"][0]["content"])
        self.assertEqual((body["options"]["num_predict"], body["think"]), (1, False))
        self.assertTrue(g.health()["providers"][0]["ok"])

    def test_ollama_without_logprobs_is_malformed(self):
        Fake.mode = "text"
        r = self.gw("ollama", model="gemma4:e4b").decide({"question": "Q?", "options": ["yes", "no"]})
        self.assertEqual(r["error"]["code"], "malformed_response")
        self.assertIn("logprobs", r["error"]["message"])

    def test_ollama_prose_answer_is_malformed(self):
        Fake.mode = "prose"
        r = self.gw("ollama", model="gemma4:e4b").decide({"question": "Q?", "options": ["yes", "no"]})
        self.assertEqual(r["error"]["code"], "malformed_response")

    def test_settings_validation(self):
        for name, settings in (("ollama", {}), ("von", {"endpoint": "http://10.0.0.5:8777"})):
            with self.subTest(name=name):
                g = Gateway(Config(provider=name, providers={name: settings}))
                self.assertTrue(g.config_errors)


if __name__ == "__main__":
    unittest.main()
