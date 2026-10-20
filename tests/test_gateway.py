import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from system1_gateway.config import Config, ConfigError, load_config
from system1_gateway.gateway import Gateway
from system1_gateway.providers import REGISTRY, ProviderError, System1Provider
from system1_gateway.schema import InvalidRequest, parse_request

Q = {"question": "Ship the release today?", "options": ["ship", "hold"]}


def gateway(provider="mock", fallback=(), timeout_s=1.0, min_confidence=0.6, **providers):
    return Gateway(Config(provider=provider, fallback=list(fallback), timeout_s=timeout_s,
                          min_confidence=min_confidence, providers=providers))


class Broken(System1Provider):
    name = "broken"

    def decide(self, request, timeout_s):
        raise ProviderError("engine down")

    def health(self, timeout_s):
        raise ProviderError("engine down")


class SchemaTests(unittest.TestCase):
    def test_minimal_request(self):
        req = parse_request({"question": "x"})
        self.assertEqual((req.options, req.context, req.min_confidence), (None, {}, None))
        self.assertTrue(req.request_id)

    def test_rejects_bad_requests(self):
        bad = [None, [], {}, {"question": ""}, {"question": "  "}, {"question": 5},
               {"question": "x" * 8001}, {"question": "x", "schema_version": "2"},
               {"question": "x", "options": ["a"]}, {"question": "x", "options": ["a", "a"]},
               {"question": "x", "options": ["a", 3]}, {"question": "x", "options": "a,b"},
               {"question": "x", "min_confidence": 1.5}, {"question": "x", "min_confidence": True},
               {"question": "x", "context": []}, {"question": "x", "request_id": ""},
               {"question": "x", "extra": 1}]
        for args in bad:
            with self.subTest(args=args):
                self.assertRaises(InvalidRequest, parse_request, args)

    def test_invalid_request_is_structured_error(self):
        r = gateway().decide({"question": "", "request_id": "abc"})
        self.assertEqual((r["status"], r["error"]["code"], r["request_id"]), ("error", "invalid_request", "abc"))

    def test_request_id_echoed_or_generated(self):
        self.assertEqual(gateway().decide({**Q, "request_id": "r-1"})["request_id"], "r-1")
        self.assertEqual(len(gateway().decide(Q)["request_id"]), 32)


class ProviderSelectionTests(unittest.TestCase):
    def test_config_selects_provider(self):
        r = gateway("mock").decide(Q)
        self.assertEqual((r["status"], r["provider"], r["decision"]), ("decided", "mock", "ship"))

    def test_unknown_provider_is_config_error(self):
        g = gateway("nope")
        self.assertEqual(g.decide(Q)["error"]["code"], "config_error")
        self.assertEqual(g.health()["status"], "down")

    def test_bad_provider_settings_are_config_error(self):
        g = gateway("laya", laya={"endpoint": "http://10.1.2.3:8765"})
        r = g.decide(Q)
        self.assertEqual(r["error"]["code"], "config_error")
        self.assertIn("not local", r["error"]["message"])


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.file = Path(self.dir.name) / "config.toml"

    def env(self, **extra):
        return {"SYSTEM1_CONFIG": str(self.file), **extra}

    def test_defaults_without_file(self):
        cfg = load_config({"APPDATA": self.dir.name, "XDG_CONFIG_HOME": self.dir.name})
        self.assertEqual((cfg.provider, cfg.fallback, cfg.source), ("laya", [], ""))

    def test_file_then_env_override(self):
        self.file.write_text('[gateway]\nprovider = "laya"\ntimeout_s = 2\n'
                             '[providers.laya]\nendpoint = "http://127.0.0.1:9000"\n', encoding="utf-8")
        cfg = load_config(self.env(SYSTEM1_PROVIDER="mock", SYSTEM1_FALLBACK="laya, mock",
                                   SYSTEM1_MOCK_CONFIDENCE="0.3", SYSTEM1_LAYA_ENDPOINT="http://localhost:1"))
        self.assertEqual((cfg.provider, cfg.fallback, cfg.timeout_s), ("mock", ["laya", "mock"], 2.0))
        self.assertEqual(cfg.providers["mock"], {"confidence": "0.3"})
        self.assertEqual(cfg.providers["laya"]["endpoint"], "http://localhost:1")

    def test_invalid_config(self):
        cases = ['[gateway]\ntimeout_s = -1\n', '[gateway]\nmin_confidence = 2\n', '[gateway]\ntypo = 1\n',
                 '[gateway]\nfallback = "mock"\n', '[gateway]\nlog_level = "LOUD"\n', 'not = [toml']
        for text in cases:
            with self.subTest(text=text):
                self.file.write_text(text, encoding="utf-8")
                self.assertRaises(ConfigError, load_config, self.env())

    def test_missing_explicit_file(self):
        self.assertRaises(ConfigError, load_config, self.env())

    def test_broken_config_does_not_crash_gateway(self):
        self.file.write_text("not = [toml", encoding="utf-8")
        with mock.patch.dict("os.environ", self.env()):
            g = Gateway()
        self.assertEqual(g.decide(Q)["error"]["code"], "config_error")


class MalformedResponseTests(unittest.TestCase):
    def test_malformed_outputs(self):
        cases = ["nope", None, [], {"decision": "ship"}, {"decision": "ship", "confidence": 1.7},
                 {"decision": "ship", "confidence": "high"}, {"decision": "ship", "confidence": True},
                 {"decision": "maybe", "confidence": 0.9}, {"decision": "", "confidence": 0.9},
                 {"decision": "ship", "confidence": 0.9, "rationale": 42}]
        for response in cases:
            with self.subTest(response=response):
                r = gateway(mock={"response": response}).decide(Q)
                self.assertEqual((r["status"], r["error"]["code"]), ("error", "malformed_response"))
                self.assertEqual(r["attempts"][0]["outcome"], "malformed")


class TimeoutTests(unittest.TestCase):
    def test_slow_provider_times_out_within_bound(self):
        started = time.monotonic()
        r = gateway(timeout_s=0.2, mock={"delay_s": 1.5}).decide(Q)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual((r["status"], r["error"]["code"]), ("error", "provider_timeout"))
        self.assertEqual(r["attempts"][0]["outcome"], "timeout")


@mock.patch.dict(REGISTRY, {"broken": Broken})
class FallbackTests(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertEqual(Config().fallback, [])
        r = gateway("broken").decide(Q)
        self.assertEqual((r["status"], r["error"]["code"], len(r["attempts"])), ("error", "provider_error", 1))

    def test_fallback_on_failure(self):
        r = gateway("broken", fallback=["mock"]).decide(Q)
        self.assertEqual((r["status"], r["provider"]), ("decided", "mock"))
        self.assertEqual([a["outcome"] for a in r["attempts"]], ["error", "ok"])

    def test_low_confidence_does_not_fall_back(self):
        with mock.patch.object(Broken, "decide", side_effect=AssertionError("fallback must not run")):
            r = gateway("mock", fallback=["broken"], mock={"confidence": 0.3}).decide(Q)
        self.assertEqual((r["status"], len(r["attempts"])), ("abstained", 1))

    def test_all_fail_reports_last_error(self):
        r = gateway("broken", fallback=["mock"], timeout_s=0.2, mock={"delay_s": 1}).decide(Q)
        self.assertEqual(r["error"]["code"], "provider_timeout")
        self.assertEqual([a["outcome"] for a in r["attempts"]], ["error", "timeout"])

    def test_health_degraded_when_primary_down(self):
        self.assertEqual(gateway("broken", fallback=["mock"]).health()["status"], "degraded")
        self.assertEqual(gateway("broken").health()["status"], "down")


class AbstentionTests(unittest.TestCase):
    def test_below_threshold_abstains(self):
        r = gateway(mock={"confidence": 0.5}).decide(Q)
        self.assertEqual((r["status"], r["decision"], r["confidence"]), ("abstained", None, 0.5))

    def test_request_threshold_overrides_config(self):
        r = gateway(mock={"confidence": 0.5}).decide({**Q, "min_confidence": 0.4})
        self.assertEqual((r["status"], r["decision"]), ("decided", "ship"))

    def test_provider_abstain(self):
        r = gateway(mock={"response": {"abstain": True, "rationale": "unsure"}}).decide(Q)
        self.assertEqual((r["status"], r["rationale"]), ("abstained", "unsure"))


class HealthAndCapabilitiesTests(unittest.TestCase):
    def test_max_options(self):
        self.assertEqual(Gateway(Config(provider="mock", providers={"mock": {"max_options": 20}})).max_options(), 20)
        self.assertIsNone(Gateway(Config(provider="mock")).max_options())
        self.assertEqual(parse_request({"question": "q", "options": [f"o{i}" for i in range(256)]}).options[0], "o0")

    def test_paused_abstains_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            pause = Path(tmp) / "paused"
            g = Gateway(Config(provider="mock", pause_file=str(pause)))
            self.assertEqual(g.decide({"question": "q", "options": ["a", "b"]})["status"], "decided")
            pause.touch()  # created after the server started: no restart needed
            r = g.decide({"question": "q", "options": ["a", "b"]})
            self.assertEqual((r["status"], r["decision"]), ("abstained", None))
            self.assertIn("paused", r["rationale"])
            self.assertEqual(g.health()["status"], "paused")

    def test_health_ok(self):
        h = gateway().health()
        self.assertEqual((h["status"], h["providers"][0]["role"]), ("ok", "primary"))

    def test_capabilities(self):
        c = gateway(fallback=["laya"]).capabilities()
        self.assertEqual(c["tools"], ["system1_decide", "system1_health", "system1_capabilities"])
        self.assertEqual(set(c["providers"]), {"mock", "laya"})
        self.assertIn("question", c["request_schema"]["required"])


class Batch(System1Provider):
    """Answers every question in one call; counts calls."""
    name = "batch"
    calls = 0

    def __init__(self, settings):
        super().__init__(settings)

    def decide(self, request, timeout_s):
        raise AssertionError("decide_many should be used")

    def decide_many(self, requests, timeout_s):
        Batch.calls += 1
        if self.settings.get("fail"):
            raise ProviderError("engine down")
        if self.settings.get("drop"):
            requests = dict(list(requests.items())[1:])
        return {k: {"decision": r.options[0], "confidence": 0.9, "probabilities": {r.options[0]: 0.9, r.options[1]: 0.1}}
                for k, r in requests.items()}

    def health(self, timeout_s):
        return {"ok": True, "detail": ""}


def batch_gateway(**settings):
    g = Gateway(Config(provider="mock"))
    g.chain = [Batch(settings)]
    return g


YN = {"a": {"question": "A?", "options": ["yes", "no"]}, "b": {"question": "B?", "options": ["yes", "no"]}}


class DecideManyTests(unittest.TestCase):
    def test_one_call_for_all_questions(self):
        Batch.calls = 0
        out = batch_gateway().decide_many(YN)
        self.assertEqual(Batch.calls, 1)
        self.assertEqual({k: (r["status"], r["decision"], r["provider"]) for k, r in out.items()},
                         {"a": ("decided", "yes", "batch"), "b": ("decided", "yes", "batch")})

    def test_batch_failure_costs_one_attempt(self):
        Batch.calls = 0
        out = batch_gateway(fail=True).decide_many(YN)
        self.assertEqual(Batch.calls, 1)
        self.assertEqual({r["status"] for r in out.values()}, {"error"})
        self.assertEqual(out["a"]["error"]["code"], "provider_error")

    def test_missing_answer_is_malformed(self):
        out = batch_gateway(drop=True).decide_many(YN)
        self.assertEqual({r["error"]["code"] for r in out.values()}, {"malformed_response"})

    def test_providers_without_batch_loop(self):
        out = Gateway(Config(provider="mock")).decide_many(YN)
        self.assertEqual({r["status"] for r in out.values()}, {"decided"})

    def test_loop_shares_one_budget(self):
        g = Gateway(Config(provider="mock", timeout_s=1.0, providers={"mock": {"delay_s": 0.4}}))
        qs = {k: {"question": f"{k}?", "options": ["yes", "no"]} for k in "abcd"}
        out = g.decide_many(qs)
        self.assertEqual(out["d"]["error"]["code"], "provider_timeout")
        self.assertIn("budget", out["d"]["error"]["message"])
        self.assertEqual(out["a"]["status"], "decided")

    def test_loop_never_exceeds_the_budget(self):
        # each answer takes 1.2 s of a 1.5 s budget: the second question may only use what is left
        g = Gateway(Config(provider="mock", timeout_s=1.5, providers={"mock": {"delay_s": 1.2}}))
        started = time.monotonic()
        out = g.decide_many({k: {"question": f"{k}?", "options": ["yes", "no"]} for k in "ab"})
        self.assertLess(time.monotonic() - started, 1.5 + 0.25)
        self.assertEqual((out["a"]["status"], out["b"]["error"]["code"]), ("decided", "provider_timeout"))

    def test_threshold_per_question(self):
        out = batch_gateway().decide_many({**YN, "b": {**YN["b"], "min_confidence": 0.95}})
        self.assertEqual((out["a"]["status"], out["b"]["status"]), ("decided", "abstained"))


if __name__ == "__main__":
    unittest.main()
