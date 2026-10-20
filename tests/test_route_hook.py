import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from system1_gateway.config import Config, ConfigError, load_config
from system1_gateway.gateway import Gateway
from system1_gateway.route_hook import NO_SKILL, TIERS, pick_skill, record_spawn, route

REPO = Path(__file__).resolve().parents[1]
PROMPT = {"hook_event_name": "UserPromptSubmit",
          "prompt": "Rename the helper function across the module and update every call site"}
SPAWN = {"hook_event_name": "PreToolUse", "tool_name": "Agent",
         "tool_input": {"description": "Rename helper", "prompt": "Rename the helper function across the module",
                        "subagent_type": "Explore", "model": "sonnet"}}


def gateway(**mock):
    return Gateway(Config(provider="mock", providers={"mock": mock}))


class NoEngine:
    """A gateway that fails the test if it is asked anything."""
    def decide(self, request):
        raise AssertionError("the engine must not be asked")

    def decide_many(self, requests):
        raise AssertionError("the engine must not be asked")


class RouteTests(unittest.TestCase):
    def test_decided_tier_becomes_hint(self):
        hint = route(PROMPT, gateway())  # mock says yes to every feature: design -> opus
        self.assertIn("**opus**", hint)
        self.assertIn('model="opus"', hint)

    def test_silent_cases(self):
        cases = [({"prompt": "yes do it"}, gateway()),                        # too short
                 ({"prompt": "Plan is ok, implement it now please"}, gateway()),  # follow-up: needs the conversation
                 ({"prompt": "/system1:doctor please check everything"}, gateway()),  # slash command
                 ({"prompt": '<agent-message from="a1"> [Subagent hand-back] done'}, gateway()),
                 ({"prompt": "<task-notification> <task-id>a1</task-id> completed"}, gateway()),
                 ({"no": "prompt"}, gateway()), ("not a dict", gateway()),
                 (PROMPT, gateway(confidence=0.3)),                           # abstained
                 (PROMPT, gateway(fail="engine down"))]                       # provider error
        for payload, g in cases:
            with self.subTest(payload=payload):
                self.assertIsNone(route(payload, g))

    def test_log_only_inside_listed_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            log, listed = Path(tmp) / "sub" / "routing.jsonl", Path(tmp) / "project"
            inside = {**PROMPT, "cwd": str(listed / "src")}
            route(inside, gateway(), str(log), [str(listed)])
            route(inside, gateway(confidence=0.3), str(log), [str(listed)])        # abstained: still logged
            route({**PROMPT, "cwd": str(Path(tmp) / "Other")}, gateway(), str(log), [str(listed)])
            route({**PROMPT, "cwd": str(listed) + "Private"}, gateway(), str(log), [str(listed)])  # prefix only
            route(PROMPT, gateway(), str(log), [str(listed)])                      # no cwd in payload
            route(inside, gateway(), str(log), [])                                 # default: nothing listed
            route({"prompt": "ok", "cwd": str(listed)}, gateway(), str(log), [str(listed)])  # too short
            entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(e["status"], e["confidence"]) for e in entries], [("decided", 0.9), ("decided", 0.3)])
        self.assertEqual((entries[0]["decision"], entries[0]["rule_tier"], entries[0]["cwd"]), ("opus", "opus", inside["cwd"]))
        self.assertEqual(set(entries[0]["features"]), {"read_only", "design", "review", "specified"})
        self.assertIsNone(entries[0]["label"])

    def test_hint_off_only_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            log, listed = Path(tmp) / "routing.jsonl", Path(tmp) / "project"
            self.assertIsNone(route({**PROMPT, "cwd": str(listed)}, gateway(), str(log), [str(listed)], hint=False))
            # outside log_dirs there is nothing to log, so the engine is not even asked
            self.assertIsNone(route({**PROMPT, "cwd": str(Path(tmp) / "other")}, NoEngine(), str(log),
                                    [str(listed)], hint=False))
            entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["status"] for e in entries], ["decided"])

    def test_record_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            log, listed = Path(tmp) / "routing.jsonl", Path(tmp) / "project"
            here = str(listed / "src")
            # asked with min_confidence 0: even a low-confidence answer is recorded as decided
            self.assertIsNone(record_spawn({**SPAWN, "cwd": here, "tool_use_id": "toolu_1"}, gateway(confidence=0.3), str(log), [str(listed)]))
            long_brief = {"prompt": "x " * 1500}  # model and subagent_type omitted
            record_spawn({**SPAWN, "cwd": here, "tool_input": long_brief}, gateway(fail="engine down"),
                         str(log), [str(listed)])
            for silent in ({**SPAWN, "cwd": str(Path(tmp) / "other")},        # not in log_dirs
                           {"hook_event_name": "PreToolUse", "cwd": here},      # no tool_input
                           {**SPAWN, "cwd": here, "tool_input": "x"},
                           {**SPAWN, "cwd": here, "tool_input": {"prompt": "  "}}):
                record_spawn(silent, NoEngine(), str(log), [str(listed)])
            first, second = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual((first["status"], first["decision"], first["source"], first["chosen"],
                          first["subagent_type"], first["tool_use_id"], first["label"]),
                         ("decided", "opus", "agent", "sonnet", "Explore", "toolu_1", None))
        self.assertEqual((second["status"], second["chosen"], second["subagent_type"], len(second["prompt"])),
                         ("error", "inherit", "general-purpose", 2000))

    def test_hint_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text('[routing]\nenabled = true\nhint = false\n', encoding="utf-8")
            self.assertFalse(load_config({"SYSTEM1_CONFIG": str(path)}).routing_hint)
            self.assertTrue(load_config({"SYSTEM1_CONFIG": str(path), "SYSTEM1_ROUTING_HINT": "true"}).routing_hint)
        self.assertTrue(Config().routing_hint)

    def test_routing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text('[routing]\nenabled = true\nlog_dirs = ["~/src/a"]\nlog_file = "x.jsonl"\n', encoding="utf-8")
            cfg = load_config({"SYSTEM1_CONFIG": str(path)})
            self.assertEqual((cfg.routing_enabled, cfg.routing_log_dirs, cfg.routing_log_file),
                             (True, ["~/src/a"], "x.jsonl"))
            env = {"SYSTEM1_CONFIG": str(path), "SYSTEM1_ROUTING_ENABLED": "false",
                   "SYSTEM1_ROUTING_LOG_DIRS": os.pathsep.join(["/x", "/y"])}
            cfg = load_config(env)
            self.assertEqual((cfg.routing_enabled, cfg.routing_log_dirs), (False, ["/x", "/y"]))
            for bad in ('[routing]\nenable = true\n', '[routing]\nlog_dirs = "/one/path"\n'):
                path.write_text(bad, encoding="utf-8")
                self.assertRaises(ConfigError, load_config, {"SYSTEM1_CONFIG": str(path)})
        self.assertEqual((Config().routing_enabled, Config().routing_log_dirs), (False, []))


SKILLS = [("alpha", "does alpha"), ("plug:beta", ""), ("gamma", "does gamma")]


class Limited(NoEngine):
    def max_options(self):
        return 3  # fewer than NO_SKILL + 3 skills


class PickSkillTests(unittest.TestCase):
    def test_hint_for_a_confident_pick(self):
        for option, name in (("alpha: does alpha", "alpha"), ("plug:beta", "plug:beta")):
            with self.subTest(name=name):
                g = gateway(response={"decision": option, "confidence": 0.95})
                self.assertIn(f"`{name}`", pick_skill(PROMPT, g, SKILLS, hint=True))

    def test_silent_cases(self):
        self.assertIsNone(pick_skill(PROMPT, gateway(), SKILLS, hint=True))           # mock picks NO_SKILL
        self.assertIsNone(pick_skill(PROMPT, gateway(response={"decision": "alpha: does alpha", "confidence": 0.7}),
                                     SKILLS, hint=True))                                # below 0.8
        self.assertIsNone(pick_skill(PROMPT, Limited(), SKILLS, hint=True))             # dormant: too many options
        self.assertIsNone(pick_skill({"prompt": "yes"}, NoEngine(), SKILLS, hint=True))
        self.assertIsNone(pick_skill(PROMPT, NoEngine(), [], hint=True))
        self.assertIsNone(pick_skill(PROMPT, NoEngine(), SKILLS, hint=False))           # nothing to log or hint

    def test_record_only_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "routing.jsonl"
            self.assertIsNone(pick_skill({**PROMPT, "cwd": tmp}, gateway(), SKILLS, str(log), [tmp]))
            (entry,) = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual((entry["source"], entry["decision"], entry["label"]), ("skill", NO_SKILL, None))

    def test_skills_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text('[skills]\nenabled = true\nhint = true\nmin_confidence = 0.9\n', encoding="utf-8")
            cfg = load_config({"SYSTEM1_CONFIG": str(path)})
            self.assertEqual((cfg.skills_enabled, cfg.skills_hint, cfg.skills_min_confidence), (True, True, 0.9))
            self.assertFalse(load_config({"SYSTEM1_CONFIG": str(path), "SYSTEM1_SKILLS_ENABLED": "false"}).skills_enabled)
            path.write_text('[skills]\nenable = true\n', encoding="utf-8")
            self.assertRaises(ConfigError, load_config, {"SYSTEM1_CONFIG": str(path)})
        self.assertEqual((Config().skills_enabled, Config().skills_hint, Config().skills_min_confidence),
                         (False, False, 0.8))


class HookProcessTests(unittest.TestCase):
    def run_hook(self, config_text: str, stdin: str, tmp: str = "", env=None) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as own:
            tmp = tmp or own
            config = Path(tmp) / "config.toml"
            config.write_text(config_text, encoding="utf-8")
            return subprocess.run([sys.executable, "-m", "system1_gateway.route_hook"], input=stdin,
                                  capture_output=True, text=True, encoding="utf-8", timeout=30, cwd=tmp,
                                  # SYSTEM1_INSTALL_DIR: never read the real pause file of the machine running the tests
                                  env={**os.environ, "PYTHONPATH": str(REPO), "SYSTEM1_CONFIG": str(config),
                                       "SYSTEM1_INSTALL_DIR": tmp, **(env or {})})

    def test_emits_hook_json_when_enabled(self):
        proc = self.run_hook('[gateway]\nprovider = "mock"\n[routing]\nenabled = true\n', json.dumps(PROMPT))
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        self.assertIn("**opus**", out["additionalContext"])

    def test_spawn_is_recorded_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).as_posix()
            config = (f'[gateway]\nprovider = "mock"\n[routing]\nenabled = true\n'
                      f'log_dirs = ["{root}"]\nlog_file = "{root}/routing.jsonl"\n')
            proc = self.run_hook(config, json.dumps({**SPAWN, "cwd": tmp}), tmp)
            entries = [json.loads(line) for line in (Path(tmp) / "routing.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))
        self.assertEqual([(e["source"], e["chosen"]) for e in entries], [("agent", "sonnet")])

    def test_skill_hint_process(self):
        payload = {**PROMPT, "availableSkills": [{"name": "alpha", "description": "does alpha"}]}
        config = ('[gateway]\nprovider = "mock"\n[providers.mock]\n'
                  'response = {decision = "alpha: does alpha", confidence = 0.95}\n[skills]\nenabled = true\nhint = true\n')
        out = json.loads(self.run_hook(config, json.dumps(payload)).stdout)["hookSpecificOutput"]
        self.assertIn("`alpha`", out["additionalContext"])

    def test_picker_skipped_when_budget_spent(self):
        # routing takes 1.4 of the 1.5 s budget, so the picker must not be asked at all: no "skill" log entry
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).as_posix()
            config = ('[gateway]\nprovider = "mock"\n[providers.mock]\ndelay_s = 1.4\n'
                      f'[routing]\nenabled = true\nhint = false\nlog_dirs = ["{root}"]\nlog_file = "{root}/routing.jsonl"\n'
                      '[skills]\nenabled = true\n')
            payload = {**PROMPT, "cwd": tmp, "availableSkills": [{"name": "alpha", "description": "does alpha"}]}
            self.run_hook(config, json.dumps(payload), tmp)
            entries = [json.loads(line) for line in (Path(tmp) / "routing.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e.get("source", "prompt") for e in entries], ["prompt"])

    def test_silent_when_paused(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "paused").touch()
            proc = self.run_hook('[gateway]\nprovider = "mock"\n[routing]\nenabled = true\n', json.dumps(PROMPT),
                                 env={"SYSTEM1_INSTALL_DIR": tmp})
            root = Path(tmp).as_posix()
            logged = (f'[gateway]\nprovider = "mock"\n[routing]\nenabled = true\n'
                      f'log_dirs = ["{root}"]\nlog_file = "{root}/routing.jsonl"\n')
            spawn = self.run_hook(logged, json.dumps({**SPAWN, "cwd": tmp}), tmp, env={"SYSTEM1_INSTALL_DIR": tmp})
            self.assertFalse((Path(tmp) / "routing.jsonl").exists())  # paused: spawns aren't recorded either
        self.assertEqual((proc.returncode, proc.stdout, spawn.stdout), (0, "", ""))

    def test_silent_when_disabled_or_broken(self):
        for config_text, stdin in (('[gateway]\nprovider = "mock"\n', json.dumps(PROMPT)),   # disabled by default
                                   ('[gateway]\nprovider = "mock"\n[routing]\nenabled = true\nhint = false\n',
                                    json.dumps(PROMPT)),
                                   ('[routing]\nenabled = true\n[gateway]\nprovider = "mock"\n', "not json"),
                                   ('not = [toml', json.dumps(PROMPT))):
            with self.subTest(config=config_text, stdin=stdin):
                proc = self.run_hook(config_text, stdin)
                self.assertEqual((proc.returncode, proc.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
