import glob
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMD = os.path.join(ROOT, "install.cmd")
SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8", newline="") as f:
        return f.read()


def without_codex(path):
    # PATH minus every folder that holds a codex launcher.
    keep = []
    for d in path.split(os.pathsep):
        if d and not any(os.path.exists(os.path.join(d, "codex" + e)) for e in (".exe", ".cmd", ".bat", "")):
            keep.append(d)
    return os.pathsep.join(keep)


class InstallTest(unittest.TestCase):
    def setUp(self):
        if os.name != "nt":
            self.skipTest("Windows only")
        self.tmp = tempfile.mkdtemp(prefix="codex setup ")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.codex = os.path.join(self.tmp, ".codex")

    def env(self, **extra):
        env = os.environ.copy()
        env.pop("CODEX_HOME", None)
        env["USERPROFILE"] = self.tmp
        env["HOME"] = self.tmp
        env.update(extra)
        return env

    def run_install(self, *args, env=None):
        r = subprocess.run(["cmd", "/c", CMD, *args], capture_output=True, text=True, encoding="utf-8",
                           env=env or self.env(), timeout=300)
        return r.returncode, r.stdout, r.stderr

    def config(self):
        with open(os.path.join(self.codex, "config.toml"), "rb") as f:
            return tomllib.load(f)

    def check(self, *extra, env=None):
        code, out, err = self.run_install("-Check", "-Json", *extra, env=env)
        doc = json.loads(out)  # stdout is one JSON document and nothing else
        return code, doc, err

    def test_parses_under_windows_powershell_51(self):
        script = os.path.join(ROOT, "install.ps1")
        cmd = ("$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
               f"'{script}', [ref]$null, [ref]$e); $e.Count; $e | ForEach-Object {{ $_.Message }}")
        r = subprocess.run([os.path.join(SYSTEM32, "WindowsPowerShell", "v1.0", "powershell.exe"),
                            "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.stdout.strip().splitlines()[0], "0", r.stdout + r.stderr)

    def test_install_into_a_temp_home(self):
        code, out, err = self.run_install("-SkipPlugins")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(read("global", "AGENTS.md"), read(self.codex, "AGENTS.md"))
        for d in glob.glob(os.path.join(ROOT, "skills", "*", "")):
            name = os.path.basename(os.path.dirname(d))
            self.assertTrue(os.path.exists(os.path.join(self.tmp, ".agents", "skills", name, "SKILL.md")), name)
        for f in glob.glob(os.path.join(ROOT, "agents", "*.toml")):
            self.assertTrue(os.path.exists(os.path.join(self.codex, "agents", os.path.basename(f))), f)
        self.assertTrue(os.path.exists(os.path.join(self.codex, "themes", "clear.tmTheme")))
        cfg = self.config()
        self.assertEqual(cfg["model"], "gpt-6.1-sol")
        self.assertEqual(cfg["approval_policy"], "never")
        self.assertEqual(cfg["tui"]["theme"], "clear")
        with open(os.path.join(self.codex, "codex-setup-state.json"), encoding="utf-8") as f:
            state = json.load(f)
        self.assertEqual(os.path.normcase(os.path.normpath(state["repo"])), os.path.normcase(os.path.normpath(ROOT)))

    def test_install_keeps_desktop_keys(self):
        os.makedirs(self.codex)
        seed = 'notify = ["a", "b"]\n\n[desktop]\nzoom = 1\nname = "keep me"\n'
        with open(os.path.join(self.codex, "config.toml"), "w", encoding="utf-8", newline="") as f:
            f.write(seed)
        code, out, err = self.run_install("-SkipPlugins")
        self.assertEqual(code, 0, out + err)
        now = read(self.codex, "config.toml")
        for line in seed.splitlines():
            if line:
                self.assertIn(line, now.splitlines())
        backups = glob.glob(os.path.join(self.codex, "backups", "codex-setup-*", "config.toml"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(read(backups[0]), seed)

    def test_codex_home_is_respected(self):
        ch = os.path.join(self.tmp, "ch")
        code, out, err = self.run_install("-SkipPlugins", env=self.env(CODEX_HOME=ch))
        self.assertEqual(code, 0, out + err)
        for rel in ("AGENTS.md", "config.toml", "codex-setup-state.json", os.path.join("themes", "clear.tmTheme")):
            self.assertTrue(os.path.exists(os.path.join(ch, rel)), rel)
        self.assertFalse(os.path.exists(self.codex))

    def test_check_json_after_install_passes(self):
        self.run_install("-SkipPlugins")
        code, doc, err = self.check("-SkipPlugins")
        self.assertEqual(code, 0, json.dumps(doc) + err)
        self.assertEqual(doc["failures"], [])
        status = {r["name"]: r["status"] for r in doc["rows"]}
        for name in ("superpowers plugin", "codex"):
            self.assertEqual(status.pop(name), "skipped")
        self.assertTrue(status)
        self.assertEqual({s for s in status.values()}, {"ok"}, status)
        for name in ("AGENTS.md", "theme clear", "config model"):
            self.assertIn(name, status)

    def test_check_writes_nothing(self):
        self.check("-SkipPlugins")
        self.assertFalse(os.path.exists(self.codex))

    def test_check_reports_config_drift(self):
        self.run_install("-SkipPlugins")
        path = os.path.join(self.codex, "config.toml")
        text = read(path)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace('model = "gpt-6.1-sol"', 'model = "x"'))
        code, doc, err = self.check("-SkipPlugins")
        self.assertEqual(code, 1)
        rows = {r["name"]: r for r in doc["rows"]}
        self.assertEqual(rows["config model"]["status"], "FAIL")
        self.assertTrue(any("config model" in f for f in doc["failures"]), doc["failures"])
        self.assertEqual(self.run_install("-SkipPlugins")[0], 0)
        self.assertEqual(self.check("-SkipPlugins")[0], 0)

    def test_check_without_codex_on_path(self):
        env = self.env(PATH=without_codex(os.environ["PATH"]))
        code, doc, err = self.check(env=env)
        self.assertEqual(code, 1)
        rows = {r["name"]: r for r in doc["rows"]}
        self.assertEqual(rows["codex"]["status"], "FAIL")
        self.assertEqual(rows["codex"]["actual"], "not on PATH")
        self.assertEqual(rows["superpowers plugin"]["status"], "FAIL")

    def test_merge_refusal_fails_the_install(self):
        os.makedirs(self.codex)
        path = os.path.join(self.codex, "config.toml")
        seed = 'tui.theme = "x"\n'
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(seed)
        code, out, err = self.run_install("-SkipPlugins")
        self.assertEqual(code, 1, out + err)
        self.assertIn("tui.theme", out + err)
        self.assertEqual(read(path), seed)

    def fake_codex(self, plugin_json, version="codex-cli 9.9.9", code=0):
        # A codex.cmd at the front of PATH; the JSON sits in a file and is `type`d, so cmd never escapes it.
        d = os.path.join(self.tmp, "fakebin")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "list.json"), "w", encoding="utf-8", newline="") as f:
            f.write(json.dumps(plugin_json))
        with open(os.path.join(d, "codex.cmd"), "w", newline="") as f:
            f.write("@echo off\r\n"
                    f"if \"%1\"==\"--version\" (echo {version}& exit /b 0)\r\n"
                    "if \"%1 %2 %3\"==\"plugin list --json\" (type \"%~dp0list.json\"& "
                    f"exit /b {code})\r\n"
                    "exit /b 1\r\n")
        return self.env(PATH=d + os.pathsep + without_codex(os.environ["PATH"]))

    def superpowers_row(self, entries, **kw):
        env = self.fake_codex({"installed": entries, "available": []}, **kw)
        code, doc, err = self.check(env=env)
        return {r["name"]: r for r in doc["rows"]}["superpowers plugin"]

    def test_superpowers_exact_id_enabled(self):
        row = self.superpowers_row([{"pluginId": "superpowers@openai-curated-remote", "installed": True, "enabled": True}])
        self.assertEqual((row["status"], row["actual"]), ("ok", "enabled"))

    def test_superpowers_lookalike_id_fails(self):
        row = self.superpowers_row([{"pluginId": "superpowers-extra@x", "installed": True, "enabled": True}])
        self.assertEqual((row["status"], row["actual"]), ("FAIL", "not enabled"))

    def test_superpowers_disabled_fails(self):
        row = self.superpowers_row([{"pluginId": "superpowers@openai-curated-remote", "installed": True, "enabled": False}])
        self.assertEqual((row["status"], row["actual"]), ("FAIL", "not enabled"))

    def test_superpowers_list_failure(self):
        row = self.superpowers_row([], code=3)
        self.assertEqual((row["status"], row["actual"]), ("FAIL", "plugin list failed"))

    def test_backups_keep_the_newest_ten(self):
        backups = os.path.join(self.codex, "backups")
        for i in range(12):
            os.makedirs(os.path.join(backups, "codex-setup-2020010%d-000000" % i if i < 10 else "codex-setup-202001%d-000000" % i))
        os.makedirs(os.path.join(backups, "other"))
        with open(os.path.join(self.codex, "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write("old" + chr(10))  # something to back up, so this run writes a backup too
        code, out, err = self.run_install("-SkipPlugins")
        self.assertEqual(code, 0, out + err)
        left = sorted(d for d in os.listdir(backups) if d.startswith("codex-setup-"))
        self.assertEqual(len(left), 10, left)
        self.assertNotIn("codex-setup-20200100-000000", left)
        self.assertTrue(left[-1] > "codex-setup-2021", left)  # this run's backup survives
        self.assertTrue(os.path.isdir(os.path.join(backups, "other")))

    def test_fresh_home_leaves_no_empty_backup(self):
        self.assertEqual(self.run_install("-SkipPlugins")[0], 0)
        backups = os.path.join(self.codex, "backups")
        self.assertEqual(os.listdir(backups) if os.path.isdir(backups) else [], [])

    def test_console_table_is_narrow_but_json_is_full(self):
        code, out, err = self.run_install("-SkipPlugins")
        self.assertEqual(code, 0, out + err)
        self.assertLessEqual(max(len(l) for l in out.splitlines()), 160, out)
        code, doc, err = self.check("-SkipPlugins")
        row = {r["name"]: r for r in doc["rows"]}["config tui.status_line"]
        self.assertGreater(len(row["expected"]), 40)
        self.assertNotIn("...", row["expected"])

    def run_ps51(self, *args):
        exe = os.path.join(SYSTEM32, "WindowsPowerShell", "v1.0", "powershell.exe")
        if not os.path.exists(exe):
            self.skipTest("powershell.exe missing")
        env = self.env()
        env.pop("PSMODULEPATH", None)  # as install.cmd does (env keys are upper-case on Windows)
        return subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                               os.path.join(ROOT, "install.ps1"), *args],
                              capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)

    def test_runs_under_windows_powershell_51(self):
        r = self.run_ps51("-SkipPlugins")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("DONE: all checks passed", r.stdout)
        self.assertEqual(self.config()["model"], "gpt-6.1-sol")
        r = self.run_ps51("-SkipPlugins", "-Check", "-Json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["failures"], [])


if __name__ == "__main__":
    unittest.main()
