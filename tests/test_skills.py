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

    def test_claude_skill_knows_when_the_run_ends(self):
        # Without a process handle, Codex can't tell a finished run from a running one and reads an empty answer.
        text = read("skills", "claude", "SKILL.md")
        self.assertIn("-PassThru", text)
        self.assertIn("HasExited", text)

    def test_setup_check_updates_codex_from_powershell(self):
        # From Git Bash, the updater's bare `tar` is Git's GNU tar, which can't extract to a C:\ path.
        text = read("skills", "setup-check", "SKILL.md")
        self.assertIn("codex update", text)
        self.assertIn("not Git Bash", text)
        # `codex update` leaves the background app-server daemon on the old version.
        self.assertIn("codex app-server daemon update", text)


if __name__ == "__main__":
    unittest.main()
