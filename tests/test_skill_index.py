import json
import tempfile
import unittest
from pathlib import Path

from system1_gateway.skill_index import available_skills, frontmatter


def skill(root: Path, folder: str, head: str):
    (root / folder).mkdir(parents=True, exist_ok=True)
    (root / folder / "SKILL.md").write_text(f"---\n{head}\n---\n\n# body\n", encoding="utf-8")


class SkillIndexTests(unittest.TestCase):
    def test_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill(Path(tmp), "a", 'name: alpha\ndescription: "Does alpha: fast"\nmetadata:\n  type: x')
            skill(Path(tmp), "b", "name: beta\ndescription: >\n  Folded text\n  over lines")
            (Path(tmp) / "c.md").write_text("---\nname: open\n", encoding="utf-8")  # unterminated
            self.assertEqual(frontmatter(Path(tmp) / "a" / "SKILL.md")["description"], "Does alpha: fast")
            self.assertEqual(frontmatter(Path(tmp) / "b" / "SKILL.md")["description"], "Folded text over lines")
            self.assertEqual(frontmatter(Path(tmp) / "c.md"), {})

    def test_disk_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude, project, plugin = Path(tmp) / ".claude", Path(tmp) / "proj", Path(tmp) / "cache" / "p1"
            skill(claude / "skills", "mine", "name: mine\ndescription: user skill")
            skill(claude / "skills", "hidden", "name: hidden\ndisable-model-invocation: true\ndescription: x")
            skill(project / ".claude" / "skills", "local", "name: local\ndescription: project skill")
            skill(plugin / "skills", "doctor", "name: doctor\ndescription: plugin skill")
            skill(Path(tmp) / "cache" / "off" / "skills", "nope", "name: nope\ndescription: disabled plugin")
            (claude / "plugins").mkdir()
            (claude / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
                "p1@market": [{"scope": "user", "installPath": str(plugin)}],
                "off@market": [{"scope": "user", "installPath": str(Path(tmp) / "cache" / "off")}]}}), encoding="utf-8")
            (claude / "settings.json").write_text(json.dumps({"enabledPlugins": {"p1@market": True, "off@market": False}}),
                                                  encoding="utf-8")
            names = [n for n, _ in available_skills({}, str(project), claude)]
        self.assertEqual(names, ["mine", "local", "p1:doctor"])

    def test_bom_and_indented_dashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            path.write_text("﻿---\nname: bom\ndisable-model-invocation: true\ndescription: |\n  a\n  ---\n  b\n---\n",
                            encoding="utf-8")
            fm = frontmatter(path)
        self.assertEqual((fm["name"], fm["disable-model-invocation"], fm["description"]), ("bom", "true", "a --- b"))

    def test_hook_list_wins(self):
        payload = {"availableSkills": [{"name": "x:y", "description": "from the hook"}, {"bad": 1}, {"name": "  "}]}
        self.assertEqual(available_skills(payload, "", Path("/nonexistent")), [("x:y", "from the hook")])


if __name__ == "__main__":
    unittest.main()
