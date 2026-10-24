import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = ("setup-check", "claude")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class SkillsTest(unittest.TestCase):
    def test_frontmatter(self):
        for name in SKILLS:
            text = read("skills", name, "SKILL.md")
            self.assertRegex(text, r"\A---\nname: %s\ndescription: Use when " % re.escape(name))
            self.assertLess(len(text.splitlines()), 80, name)

    def test_setup_check_steps(self):
        text = read("skills", "setup-check", "SKILL.md")
        for word in ("codex-setup-state.json", 'install.cmd" -Check -Json', "codex doctor",
                     "git -C <repo> branch --show-current", "main checkout"):
            self.assertIn(word, text)

    def test_claude_skill_commands(self):
        text = read("skills", "claude", "SKILL.md")
        self.assertRegex(text, r'claude -p [^\n]*< "[^"]*brief[^"]*"')
        self.assertIn("--permission-mode dontAsk --allowedTools Read Grep Glob", text)
        self.assertIn("verify", text.lower())
        self.assertIn("claude-answer.md", text)


if __name__ == "__main__":
    unittest.main()
