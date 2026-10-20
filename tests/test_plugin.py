import json
import unittest
from pathlib import Path

import system1_gateway

REPO = Path(__file__).resolve().parents[1]


class PluginManifestTests(unittest.TestCase):
    def test_plugin_version_matches_package(self):
        # Claude Code only offers plugin updates when this version changes, so it must follow __version__.
        manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], system1_gateway.__version__)

    def test_agent_spawns_are_recorded(self):
        hooks = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        (entry,) = hooks["PreToolUse"]
        # anchored: matchers are unanchored regexes, and "Agent|Task" would also fire on TaskCreate, TaskUpdate, ...
        # "Task" is the tool's name in older Claude Code
        self.assertEqual(entry["matcher"], "^(Agent|Task)$")
        self.assertIn("hooks/route", entry["hooks"][0]["command"])

    def test_toggle_is_user_only(self):
        # user-only skills never put their description into a session's context
        text = (REPO / "skills" / "toggle" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", text.split("---")[1])

    def test_calibrate_skill_covers_features_and_outcomes(self):
        text = (REPO / "skills" / "calibrate" / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("feature_labels", "scripts/outcomes.py", "scripts/evaluate.py"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
