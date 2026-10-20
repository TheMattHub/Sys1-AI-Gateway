import unittest

from system1_gateway.config import Config
from system1_gateway.gateway import Gateway
from system1_gateway.routing_features import FEATURES, YES_NO, ask_features, requests_for
from system1_gateway.routing_rule import tier


class RuleTests(unittest.TestCase):
    def test_table(self):
        cases = [({"design": "yes", "review": "no", "read_only": "no"}, "opus"),
                 ({"design": "no", "review": "yes", "read_only": "yes"}, "opus"),
                 ({"design": "no", "review": "no", "read_only": "yes"}, "haiku"),
                 ({"design": "no", "review": "no", "read_only": "no", "specified": "yes"}, "sonnet"),
                 ({"design": None, "review": "no", "read_only": "no"}, None),
                 ({}, None)]
        for answers, expected in cases:
            with self.subTest(answers=answers):
                self.assertEqual(tier(answers), expected)


class FeatureTests(unittest.TestCase):
    def test_requests(self):
        reqs = requests_for("x" * 5000)
        self.assertEqual(set(reqs), set(FEATURES))
        self.assertTrue(all(r["options"] == YES_NO and r["min_confidence"] == 0.0 for r in reqs.values()))
        self.assertEqual(len(reqs["design"]["context"]["task"]), 2000)

    def test_ask_features(self):
        f = ask_features(Gateway(Config(provider="mock")), "Rename the helper")  # mock: first option, 0.9
        self.assertEqual({v["answer"] for v in f.values()}, {"yes"})
        f = ask_features(Gateway(Config(provider="mock", providers={"mock": {"fail": "down"}})), "x")
        self.assertEqual({(v["answer"], v["status"]) for v in f.values()}, {(None, "error")})


class ClassifyTests(unittest.TestCase):
    def test_partial_error_is_error_not_abstained(self):
        from system1_gateway.route_hook import classify

        class Mixed:
            chain = []

            def decide_many(self, requests):
                ok = {"status": "decided", "decision": "no", "confidence": 0.9}
                return {k: (ok if k != "design" else {"status": "error", "decision": None, "confidence": None})
                        for k in requests}
        self.assertEqual(classify(Mixed(), "Rename the helper")["status"], "error")


if __name__ == "__main__":
    unittest.main()
