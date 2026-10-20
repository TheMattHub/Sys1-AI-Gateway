import unittest

import fake_laya
from system1_gateway.config import Config
from system1_gateway.gateway import Gateway
from system1_gateway.providers.laya import LayaProvider

# Verbatim laya-serve 0.3.20 reply (typed-decisions on CUDA), captured 2026-09-24.
REAL_CHOICE_REPLY = {
    "model": "laya-rl-agent",
    "answers": {"decision": {"type": "choice", "choice": "block the merge",
                             "probabilities": {"rerun the pipeline": 0.479, "block the merge": 0.521},
                             "confidence": 0.0013, "answer_confidence": 0.521, "action": {"act_probability": 1.0}}},
    "usage": {"input_tokens": 59, "output_tokens": 0},
    "routing": {"model": "typed-decisions", "repo": "convaiinnovations/laya/typed-decisions",
                "reason": "explicit model='typed-decisions'", "detection": None, "workflow": None},
}
RERUN_OR_BLOCK = {"question": "What should we do with this failed CI run?",
                  "options": ["rerun the pipeline", "block the merge"]}


class LayaAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = fake_laya.start()
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        fake_laya.Handler.canned = None
        fake_laya.Handler.requests.clear()

    def gateway(self, timeout_s=3.0, min_confidence=0.6, **laya):
        return Gateway(Config(provider="laya", timeout_s=timeout_s, min_confidence=min_confidence,
                              providers={"laya": {"endpoint": self.endpoint, **laya}}))

    def last_request(self):
        return fake_laya.Handler.requests[-1]

    def test_choice_request_and_mapping(self):
        r = self.gateway().decide({"question": "Should we deploy the hotfix now?",
                                   "options": ["deploy the hotfix", "wait for review"],
                                   "context": {"severity": "high"}})
        self.assertEqual((r["status"], r["decision"], r["provider"]), ("decided", "deploy the hotfix", "laya"))
        self.assertIn("deploy the hotfix=", r["rationale"])
        body = self.last_request()["body"]
        self.assertEqual(body["model"], "typed-decisions")
        self.assertEqual(body["state"], {"severity": "high"})
        self.assertEqual(body["questions"]["decision"], {"type": "choice", "instructions": "Should we deploy the hotfix now?",
                                                         "criteria": ["deploy the hotfix", "wait for review"]})

    def test_real_reply_uses_answer_confidence(self):
        fake_laya.Handler.canned = REAL_CHOICE_REPLY
        r = self.gateway(min_confidence=0.5).decide(RERUN_OR_BLOCK)
        self.assertEqual((r["status"], r["decision"], r["confidence"]), ("decided", "block the merge", 0.521))
        self.assertEqual(r["rationale"], "laya typed-decisions: block the merge=0.52, rerun the pipeline=0.48")
        # Same reply under the default 0.6 threshold: a near coin-flip abstains.
        self.assertEqual(self.gateway().decide(RERUN_OR_BLOCK)["status"], "abstained")

    def test_free_form_question_is_yes_no_choice_not_noul(self):
        # noul follows its labels (called rm -rf "safe" live), so yes/no goes out as a two-option choice.
        fake_laya.Handler.canned = {"answers": {"decision": {"type": "choice", "choice": "yes", "answer_confidence": 0.7,
                                                             "probabilities": {"yes": 0.7, "no": 0.3}}},
                                    "routing": {"model": "typed-decisions"}}
        r = self.gateway().decide({"question": "Is this tool call destructive?", "context": {"cmd": "rm -rf /"}})
        self.assertEqual((r["status"], r["decision"], r["probabilities"]), ("decided", "yes", {"yes": 0.7, "no": 0.3}))
        self.assertEqual(self.last_request()["body"]["questions"]["decision"],
                         {"type": "choice", "instructions": "Is this tool call destructive?", "criteria": ["yes", "no"]})

    def test_too_many_options_refused(self):
        r = self.gateway().decide({"question": "Which label?", "options": [f"label {i}" for i in range(21)]})
        self.assertEqual(r["error"]["code"], "provider_error")
        self.assertIn("at most 20", r["error"]["message"])
        self.assertEqual(fake_laya.Handler.requests, [])  # never sent

    def test_non_latin_text_abstains_on_english_only_checkpoint(self):
        hindi = {"question": "क्या यह टिकट बिलिंग के बारे में है?", "options": ["हाँ", "नहीं"]}
        r = self.gateway().decide(hindi)
        self.assertEqual(r["status"], "abstained")
        self.assertIn("non-Latin", r["rationale"])
        self.assertEqual(fake_laya.Handler.requests, [])
        italian = {"question": "Rinomina la variabile userId in accountId nel file utils.py",
                   "options": ["rinomina la variabile", "lascia com'è"]}
        self.gateway(min_confidence=0.0).decide(italian)
        self.assertEqual(len(fake_laya.Handler.requests), 1)  # Latin script: sent normally
        self.gateway(model="multilingual", min_confidence=0.0).decide(hindi)
        self.assertEqual(len(fake_laya.Handler.requests), 2)  # multilingual checkpoint: sent

    def test_no_overlap_abstains(self):
        r = self.gateway().decide({"question": "zzz", "options": ["alpha", "beta"]})
        self.assertEqual((r["status"], r["decision"]), ("abstained", None))

    def test_wrong_checkpoint_is_malformed(self):
        fake_laya.Handler.canned = {**REAL_CHOICE_REPLY, "routing": {"model": "english"}}
        r = self.gateway().decide(RERUN_OR_BLOCK)
        self.assertEqual(r["error"]["code"], "malformed_response")
        self.assertIn("'english'", r["error"]["message"])

    def test_auto_routing_when_model_empty(self):
        fake_laya.Handler.canned = {**REAL_CHOICE_REPLY, "routing": {"model": "english"}}
        r = self.gateway(model="", min_confidence=0.5).decide(RERUN_OR_BLOCK)
        self.assertEqual(r["status"], "decided")
        self.assertNotIn("model", self.last_request()["body"])

    def test_malformed_bodies(self):
        routed = {"model": "typed-decisions"}
        cases = [({"answers": {}, "routing": routed}, RERUN_OR_BLOCK),
                 ({"answers": {"decision": {"type": "noul", "noul": "high"}}, "routing": routed}, {"question": "ok?"}),
                 (["not", "an", "object"], {"question": "ok?"})]
        for canned, question in cases:
            with self.subTest(canned=canned):
                fake_laya.Handler.canned = canned
                self.assertEqual(self.gateway().decide(question)["error"]["code"], "malformed_response")

    def test_http_error_keeps_server_detail(self):
        r = self.gateway().decide({"question": "__fail__"})
        self.assertEqual(r["error"]["code"], "provider_error")
        self.assertIn("boom", r["error"]["message"])

    def test_non_json(self):
        self.assertEqual(self.gateway().decide({"question": "__garbage__"})["error"]["code"], "malformed_response")

    def test_timeout(self):
        r = self.gateway(timeout_s=0.3).decide({"question": "__slow__"})
        self.assertEqual(r["error"]["code"], "provider_timeout")

    def test_api_key_sent_as_bearer(self):
        self.gateway(api_key="s3cret").decide({"question": "ok?"})
        self.assertEqual(self.last_request()["authorization"], "Bearer s3cret")
        self.gateway().decide({"question": "ok?"})
        self.assertIsNone(self.last_request()["authorization"])

    def test_health(self):
        h = self.gateway().health()
        self.assertEqual(h["status"], "ok")
        self.assertIn("typed-decisions", h["providers"][0]["detail"])
        self.assertIn("not preloaded", self.gateway(model="multilingual").health()["providers"][0]["detail"])

    def test_invalid_settings(self):
        for settings in ({"endpoint": "http://10.1.2.3:8765"}, {"endpoint": "https://laya.example.com"},
                         {"endpoint": "ftp://127.0.0.1"}, {"endpoint": "nonsense"}, {"model": "laya-7b"}):
            with self.subTest(settings=settings):
                self.assertRaises(ValueError, LayaProvider, settings)
        self.assertEqual(self.gateway(model="laya-7b").decide({"question": "ok?"})["error"]["code"], "config_error")
        LayaProvider({"endpoint": "http://localhost:8765"})
        LayaProvider({"endpoint": "http://[::1]:8765"})
        LayaProvider({"endpoint": "https://laya.example.com", "allow_remote": "true"})


    def test_decide_many_is_one_request(self):
        fake_laya.Handler.requests.clear()
        qs = {"read_only": {"question": "Only a lookup?", "options": ["yes", "no"], "context": {"task": "count files"}},
              "design": {"question": "Design work?", "options": ["yes", "no"], "context": {"task": "count files"}}}
        out = self.gateway(min_confidence=0.0).decide_many(qs)
        self.assertEqual(len(fake_laya.Handler.requests), 1)
        body = self.last_request()["body"]
        self.assertEqual(set(body["questions"]), {"read_only", "design"})
        self.assertEqual(body["state"], {"task": "count files"})
        self.assertEqual({r["status"] for r in out.values()}, {"decided"})


if __name__ == "__main__":
    unittest.main()
