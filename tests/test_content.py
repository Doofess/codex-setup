import plistlib
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def theme_setting(theme, *scopes):
    for item in theme["settings"]:
        scope = item.get("scope", "")
        names = [s.strip() for s in scope.split(",")]
        if any(s in names for s in scopes):
            return item["settings"]
    raise AssertionError(f"no setting for {scopes}")


class ContentTests(unittest.TestCase):
    def test_rules_fit_codex_budget(self):
        self.assertLess(len((ROOT / "global/AGENTS.md").read_bytes()), 8192)

    def test_rules_name_the_decided_models(self):
        text = read("global/AGENTS.md")
        for word in ["gpt-6.1-sol", "gpt-6-astra", "worker", "explorer",
                     "$claude", "$setup-check", "C:/dev/codex-setup"]:
            self.assertIn(word, text)

    def test_rules_have_no_claude_only_words(self):
        text = read("global/AGENTS.md")
        for word in ["advisor", "Opus", "Sonnet", "Haiku", "Fable", "/effort",
                     "CLAUDE.md", ".mcp.json", "install.ps1 -SkipPlugins"]:
            self.assertNotIn(word, text)

    def test_agents(self):
        want = {
            "worker": ("gpt-6.1-sol", "medium"),
            "worker_high": ("gpt-6.1-sol", "high"),
            "explorer": ("gpt-6-luna", "low"),
        }
        files = sorted((ROOT / "agents").glob("*.toml"))
        self.assertEqual([f.stem for f in files], sorted(want))
        for f in files:
            data = tomllib.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], f.stem)
            self.assertEqual((data["model"], data["model_reasoning_effort"]), want[f.stem])
            self.assertTrue(data["description"].strip())
            self.assertTrue(data["developer_instructions"].strip())

    def test_rules_send_hard_work_to_worker_high(self):
        # A spawn's own effort may not override the agent file's, so high effort is its own agent.
        rules = read("global/AGENTS.md")
        self.assertIn("`worker_high`", rules)
        self.assertNotIn("with high effort for", rules)

    def test_explorer_says_read_only(self):
        data = tomllib.loads(read("agents/explorer.toml"))
        text = data["developer_instructions"].lower()
        self.assertIn("read-only", text)
        self.assertIn("do not edit", text)

    def test_theme(self):
        theme = plistlib.loads((ROOT / "themes/clear.tmTheme").read_bytes())
        self.assertEqual(theme["name"], "clear")
        for scope in ("markup.inserted", "diff.inserted"):
            self.assertEqual(theme_setting(theme, scope)["background"].upper(), "#005F00")
        for scope in ("markup.deleted", "diff.deleted"):
            self.assertEqual(theme_setting(theme, scope)["background"].upper(), "#5F0000")
        raw = theme_setting(theme, "markup.inline.raw", "markup.raw.inline")
        self.assertEqual(raw["foreground"].upper(), "#3B78FF")

    def test_presets_parse(self):
        files = sorted((ROOT / "mcp-presets").glob("*.toml"))
        self.assertEqual([f.name for f in files], ["cluster.toml", "web.toml"])
        for f in files:
            data = tomllib.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(list(data), ["mcp_servers"])
            self.assertTrue(data["mcp_servers"])
            self.assertNotIn("${", f.read_text(encoding="utf-8").replace("${VAR}", ""))


if __name__ == "__main__":
    unittest.main()
