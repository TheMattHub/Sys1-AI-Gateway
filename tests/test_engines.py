import importlib.util
import json
import math
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

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
        if self.path.startswith("/v1/models/"):
            return self._send({"id": "claude-haiku-5-5-20261001", "type": "model"})
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
        if self.path == "/v1/messages" and Fake.mode == "redirect":
            self.send_response(307)
            self.send_header("Location", "/stolen")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/v1/messages":
            Fake.key = self.headers.get("x-api-key")  # case-insensitive lookup
            names = body["tools"][0]["input_schema"]["properties"]["ranking"]["items"]["enum"]
            use = {"ranking": [names[-1], "not an option"], "confidence": 0.7}
            content = [{"type": "tool_use", "name": "choose", "input": use}] if Fake.mode != "text" else [{"type": "text", "text": "B"}]
            return self._send({"content": content, "usage": {"input_tokens": 10, "output_tokens": 5}})
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

    def test_systemone_sends_model_only_when_set(self):
        g = self.gw("systemone")
        r = g.decide({"question": "Tier?", "options": ["haiku", "opus"], "context": {"task": "x"}})
        self.assertEqual((r["status"], r["decision"], r["provider"]), ("decided", "haiku", "systemone"))
        self.assertNotIn("model", Fake.requests[-1][1])
        self.gw("systemone", model="d1-3b").decide({"question": "Q?", "options": ["a", "b"]})
        self.assertEqual(Fake.requests[-1][1]["model"], "d1-3b")
        self.assertTrue(g.health()["providers"][0]["ok"])

    def test_anthropic_forced_tool_call(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-not-real"}):
            g = self.gw("anthropic")
            r = g.decide({"question": "Tier?", "options": ["haiku", "opus"], "context": {"task": "Rename x"}})
            self.assertEqual((r["status"], r["decision"], r["confidence"]), ("decided", "opus", 0.7))
            self.assertEqual(Fake.key, "test-key-not-real")
            body = Fake.requests[-1][1]
            self.assertEqual((body["model"], body["tool_choice"]["name"]), ("claude-haiku-5-5", "choose"))
            self.assertEqual(body["messages"][0]["content"], "Rename x")
            self.assertNotIn("test-key-not-real", json.dumps(r))
            self.assertTrue(g.health()["providers"][0]["ok"])
            Fake.mode = "text"
            self.assertEqual(g.decide({"question": "Q?", "options": ["a", "b"]})["error"]["code"], "malformed_response")

    def test_anthropic_refuses_redirects(self):
        Fake.mode = "redirect"
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-not-real"}):
            r = self.gw("anthropic").decide({"question": "Q?", "options": ["a", "b"]})
        self.assertEqual(r["error"]["code"], "provider_error")
        self.assertNotIn("/stolen", [path for path, _ in Fake.requests])

    def test_anthropic_needs_key_and_https(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(self.gw("anthropic").config_errors)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
            g = Gateway(Config(provider="anthropic", providers={"anthropic": {"endpoint": "http://example.com"}}))
            self.assertTrue(g.config_errors)

    def test_settings_validation(self):
        for name, settings in (("ollama", {}), ("von", {"endpoint": "http://10.0.0.5:8777"})):
            with self.subTest(name=name):
                g = Gateway(Config(provider=name, providers={name: settings}))
                self.assertTrue(g.config_errors)


class ServeScriptTests(unittest.TestCase):
    """engines/systemone/serve.py with a fake chooser (no torch), driven through the systemone provider."""

    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "engines" / "systemone" / "serve.py"
        spec = importlib.util.spec_from_file_location("serve", path)
        serve = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(serve)
        cls.seen = []

        def choose(state, instructions, criteria):
            cls.seen.append((state, instructions, dict(criteria)))
            return serve.softmax({n: float(len(n)) for n in criteria})
        cls.servers = [ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(choose, "fake", tok)) for tok in ("", "s3cret")]
        for srv in cls.servers:
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        cls.url, cls.token_url = (f"http://127.0.0.1:{srv.server_port}" for srv in cls.servers)

    @classmethod
    def tearDownClass(cls):
        for srv in cls.servers:
            srv.shutdown()
            srv.server_close()

    def post(self, body, headers, url=None):
        import urllib.error
        import urllib.request
        req = urllib.request.Request((url or self.url) + "/v1/systemone", body, headers, method="POST")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_refuses_foreign_host_form_posts_big_bodies_and_too_many_options(self):
        ok = json.dumps({"state": "s", "questions": {"q": {"type": "choice", "criteria": {"a": "a", "b": "b"}}}}).encode()
        js = {"Content-Type": "application/json"}
        self.assertEqual(self.post(ok, js), 200)
        self.assertEqual(self.post(ok, {**js, "Host": "evil.example:80"}), 403)
        self.assertEqual(self.post(ok, {"Content-Type": "text/plain"}), 415)
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.servers[0].server_port, timeout=5)
        c.putrequest("POST", "/v1/systemone")
        c.putheader("Content-Type", "application/json")
        c.putheader("Content-Length", "2000000")    # announced, never sent: refused before reading
        c.endheaders()
        self.assertEqual(c.getresponse().status, 413)
        c.close()
        many = {"state": "s", "questions": {"q": {"type": "choice", "criteria": {str(i): "" for i in range(300)}}}}
        self.assertEqual(self.post(json.dumps(many).encode(), js), 422)

    def test_bearer_token_when_set(self):
        ok = json.dumps({"state": "s", "questions": {"q": {"type": "choice", "criteria": {"a": "a", "b": "b"}}}}).encode()
        js = {"Content-Type": "application/json"}
        self.assertEqual(self.post(ok, js, self.token_url), 401)
        self.assertEqual(self.post(ok, {**js, "Authorization": "Bearer s3cret"}, self.token_url), 200)
        g = Gateway(Config(provider="systemone", min_confidence=0.0,
                           providers={"systemone": {"endpoint": self.token_url, "api_key": "s3cret"}}))
        self.assertEqual(g.decide({"question": "Which?", "options": ["ab", "abcd"]})["status"], "decided")

    def test_choice_through_provider(self):
        g = Gateway(Config(provider="systemone", min_confidence=0.0, providers={"systemone": {"endpoint": self.url}}))
        r = g.decide({"question": "Which?", "options": ["ab", "abcd"], "context": {"task": "pick"}})
        self.assertEqual((r["status"], r["decision"]), ("decided", "abcd"))
        self.assertEqual(self.seen[-1][:2], ('{"task": "pick"}', "Which?"))
        self.assertAlmostEqual(sum(r["probabilities"].values()), 1.0, places=6)
        self.assertTrue(g.health()["providers"][0]["ok"])


if __name__ == "__main__":
    unittest.main()
