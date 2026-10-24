import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import codex_config

with open(os.path.join(ROOT, "config", "codex.toml"), encoding="utf-8") as f:
    TEMPLATE = f.read()
OWNED = codex_config.owned(TEMPLATE)


def get(doc, table, key):
    for part in filter(None, table.split(".")):
        doc = doc[part]
    return doc[key]


class MergeTest(unittest.TestCase):
    def assert_owned(self, text):
        doc = tomllib.loads(text.lstrip("\ufeff"))
        for table, keys in OWNED.items():
            for key, value in keys.items():
                self.assertEqual(get(doc, table, key), value, f"{table}.{key}")
        return doc

    def test_adds_keys_to_empty_file(self):
        self.assert_owned(codex_config.merge("", OWNED))

    def test_replaces_existing_values_and_keeps_everything_else(self):
        src = (
            "# the model\n"
            'model = "gpt-6-astra"\n'
            'model_reasoning_effort = "high"\n'
            "# set by the app\n"
            'notify = ["x.exe", "turn-ended"]\n'
            "\n"
            "# tui comment\n"
            "[tui]\n"
            "screen_reader_detection_done = true\n"
            "\n"
            "# desktop comment\n"
            "[desktop]\n"
            'followUpQueueMode = "steer"\n'
            "\n"
            "# projects comment\n"
            "[projects.'c:\\dev\\inwire']\n"
            'trust_level = "trusted"\n'
        )
        out = codex_config.merge(src, OWNED)
        doc = self.assert_owned(out)
        self.assertEqual(doc["model"], "gpt-6.1-sol")
        self.assertIs(doc["tui"]["screen_reader_detection_done"], True)
        self.assertEqual(doc["desktop"], {"followUpQueueMode": "steer"})
        self.assertEqual(doc["projects"]["c:\\dev\\inwire"], {"trust_level": "trusted"})
        self.assertEqual(doc["notify"], ["x.exe", "turn-ended"])
        for line in src.splitlines():
            if line.startswith("#"):
                self.assertIn(line + "\n", out)

    def test_root_keys_go_before_the_first_table(self):
        src = '# top\n\n[desktop]\nfollowUpQueueMode = "steer"\n'
        out = codex_config.merge(src, OWNED)
        doc = self.assert_owned(out)
        self.assertNotIn("model", doc["desktop"])
        self.assertLess(out.index("model ="), out.index("[desktop]"))
        self.assertTrue(out.startswith("# top\n"))

    def test_root_keys_follow_existing_root_keys(self):
        out = codex_config.merge('notify = ["a"]\n\n[desktop]\nx = 1\n', OWNED)
        self.assert_owned(out)
        self.assertLess(out.index("notify"), out.index("model ="))
        self.assertLess(out.index("sandbox_mode"), out.index("[desktop]"))

    def test_new_table_is_appended(self):
        src = 'model = "a"\n\n[tui]\ntheme = "x"\n'
        out = codex_config.merge(src, OWNED)
        self.assert_owned(out)
        self.assertGreater(out.index("[features]"), out.index("[tui]"))
        self.assertEqual(out.count("[features]"), 1)

    def test_existing_table_gets_the_missing_key(self):
        src = "[tui]\nstatus_line_use_colors = true\nstatus_line = []\n\n[desktop]\nx = 1\n"
        out = codex_config.merge(src, OWNED)
        doc = self.assert_owned(out)
        self.assertEqual(out.count("[tui]"), 1)
        self.assertEqual(doc["desktop"], {"x": 1})
        self.assertLess(out.index('theme = "clear"'), out.index("[desktop]"))

    def test_subtable_header_is_not_the_table(self):
        src = "[tui.notifications]\nfoo = true\n"
        out = codex_config.merge(src, OWNED)
        doc = self.assert_owned(out)
        self.assertEqual(doc["tui"]["notifications"], {"foo": True})
        self.assertEqual(out.count("[tui.notifications]"), 1)
        self.assertEqual(out.count("[tui]"), 1)

    def test_array_of_tables_header_ends_a_region(self):
        src = "[tui]\nx = 1\n[[hooks]]\ntheme = 2\n"
        out = codex_config.merge(src, OWNED)
        doc = self.assert_owned(out)
        self.assertEqual(doc["hooks"], [{"theme": 2}])

    def test_multiline_array_is_replaced_whole(self):
        src = '[tui]\nstatus_line = [\n  "git-branch",\n  "a]b",\n]\ntheme = "x"\n'
        out = codex_config.merge(src, OWNED)
        self.assert_owned(out)
        self.assertNotIn("a]b", out)

    def test_bracket_in_string_does_not_end_the_array(self):
        src = '[tui]\nstatus_line = [\n  "]",\n  # ] in a comment\n  "[x",\n]\nstatus_line_use_colors = false\n'
        out = codex_config.merge(src, OWNED)
        self.assert_owned(out)

    def test_header_lookalike_inside_multiline_string_is_not_a_header(self):
        src = 'note = """\n[tui]\ntheme = "no"\n"""\n'
        out = codex_config.merge(src, OWNED)
        doc = self.assert_owned(out)
        self.assertEqual(doc["note"], '[tui]\ntheme = "no"\n')

    def test_crlf_and_bom_are_preserved(self):
        src = '\ufeffmodel = "a"\r\n[tui]\r\nx = 1'
        out = codex_config.merge(src, OWNED)
        self.assert_owned(out)
        self.assertTrue(out.startswith('\ufeffmodel = "gpt-6.1-sol"\r\n'))
        self.assertNotIn("\n", out.replace("\r\n", ""))
        self.assertFalse(out.endswith("\n"))
        self.assertEqual(out.count("\ufeff"), 1)

    def test_lf_file_stays_lf_and_keeps_final_newline(self):
        out = codex_config.merge("[tui]\nx = 1\n", OWNED)
        self.assertNotIn("\r", out)
        self.assertTrue(out.endswith("\n"))

    def test_dotted_root_key_is_refused(self):
        with self.assertRaises(codex_config.MergeError) as ctx:
            codex_config.merge('tui.theme = "x"\n', OWNED)
        self.assertIn("tui.theme", str(ctx.exception))

    def test_inline_table_is_refused(self):
        with self.assertRaises(codex_config.MergeError) as ctx:
            codex_config.merge('tui = { theme = "x" }\n', OWNED)
        self.assertIn("tui.theme", str(ctx.exception))

    def test_array_of_tables_for_an_owned_table_is_refused(self):
        with self.assertRaises(codex_config.MergeError) as ctx:
            codex_config.merge('[[tui]]\ntheme = "x"\n', OWNED)
        self.assertIn("[[tui]]", str(ctx.exception))
        self.assertIn("tui.theme", str(ctx.exception))
        self.assertNotIn("invalid TOML", str(ctx.exception))

    def test_array_of_tables_prefix_of_an_owned_table_is_refused(self):
        with self.assertRaises(codex_config.MergeError) as ctx:
            codex_config.merge("[[features]]\nx = 1\n", OWNED)
        self.assertIn("[[features]]", str(ctx.exception))
        self.assertIn("features.fast_mode", str(ctx.exception))

    def test_deeper_array_of_tables_does_not_block_the_merge(self):
        out = codex_config.merge("[[tui.foo]]\nx = 1\n", OWNED)
        doc = self.assert_owned(out)
        self.assertEqual(doc["tui"]["foo"], [{"x": 1}])

    def test_trailing_comment_is_kept(self):
        out = codex_config.merge('model = "old"  # my note\n', OWNED)
        self.assert_owned(out)
        self.assertIn('model = "gpt-6.1-sol"  # my note\n', out)

    def test_line_without_a_comment_gets_no_trailing_space(self):
        out = codex_config.merge('model = "old"   \n', OWNED)
        self.assertIn('model = "gpt-6.1-sol"\n', out)
        out = codex_config.merge('model = "old"\n', OWNED)
        self.assertIn('model = "gpt-6.1-sol"\n', out)

    def test_hash_inside_the_old_string_is_not_a_comment(self):
        out = codex_config.merge("model = \"a#b\"  # c\nmodel_reasoning_effort = 'x#y'\n", OWNED)
        self.assert_owned(out)
        self.assertIn('model = "gpt-6.1-sol"  # c\n', out)
        self.assertNotIn("a#b", out)
        self.assertNotIn("x#y", out)
        out = codex_config.merge('model = "a#b"\n', OWNED)
        self.assertIn('model = "gpt-6.1-sol"\n', out)

    def test_multiline_array_keeps_only_the_comment_after_the_closing_bracket(self):
        src = '[tui]\nstatus_line = [  # old list\n  "a",  # first\n  "b",\n]  # end note\ntheme = "x"\n'
        out = codex_config.merge(src, OWNED)
        self.assert_owned(out)
        self.assertIn("]  # end note\n", out)
        self.assertNotIn("old list", out)
        self.assertNotIn("first", out)

    def test_comment_after_a_multiline_string_close_is_kept(self):
        src = 'model = """\nold # not a comment\n"""  # kept\n'
        out = codex_config.merge(src, OWNED)
        self.assert_owned(out)
        self.assertIn('model = "gpt-6.1-sol"  # kept\n', out)
        self.assertNotIn("not a comment", out)

    def test_trailing_comment_keeps_crlf(self):
        out = codex_config.merge('model = "old" # note\r\n[tui]\r\nx = 1\r\n', OWNED)
        self.assert_owned(out)
        self.assertIn('model = "gpt-6.1-sol" # note\r\n', out)
        self.assertNotIn("\n", out.replace("\r\n", ""))

    def test_bom_is_written_as_an_escape(self):
        with open(codex_config.__file__, "rb") as f:
            self.assertFalse(b"\xef\xbb\xbf" in f.read())
        self.assertEqual(codex_config.BOM, "\ufeff")

    def test_invalid_input_is_refused(self):
        with self.assertRaises(codex_config.MergeError) as ctx:
            codex_config.merge("model = \n[", OWNED)
        self.assertIn("not valid TOML", str(ctx.exception))

    def test_merge_is_idempotent(self):
        once = codex_config.merge("[desktop]\nx = 1\n", OWNED)
        self.assertEqual(codex_config.merge(once, OWNED), once)

    def assert_other_keys_survive(self, src):
        out = codex_config.merge(src, OWNED)
        doc = self.assert_owned(out)
        self.assertEqual(doc["desktop"]["followUpQueueMode"], "steer")
        self.assertIs(doc["tui"]["screen_reader_detection_done"], True)
        self.assertEqual(doc["tui"]["status_line"], OWNED["tui"]["status_line"])

    def test_four_quote_multiline_string_keeps_other_keys(self):
        self.assert_other_keys_survive(
            '[features]\nfast_mode = false\n[tui]\nstatus_line = ["""git-branch""""]\n'
            'screen_reader_detection_done = true\n[desktop]\nfollowUpQueueMode = "steer"\n'
        )

    def test_four_quote_literal_multiline_string_keeps_other_keys(self):
        self.assert_other_keys_survive(
            "[features]\nfast_mode = false\n[tui]\nstatus_line = ['''git-branch'''']\n"
            'screen_reader_detection_done = true\n[desktop]\nfollowUpQueueMode = "steer"\n'
        )

    def test_unowned_change_is_refused(self):
        real = codex_config._set_key

        def lossy(lines, nl, table, key, value):
            real(lines, nl, table, key, value)
            lines[:] = [ln for ln in lines if "followUpQueueMode" not in ln[0]]

        src = '[tui]\nx = 1\n[desktop]\nfollowUpQueueMode = "steer"\n'
        with mock.patch.object(codex_config, "_set_key", lossy), self.assertRaises(codex_config.MergeError) as ctx:
            codex_config.merge(src, OWNED)
        self.assertIn("desktop.followUpQueueMode", str(ctx.exception))

    def test_unowned_type_change_is_refused(self):
        real = codex_config._set_key

        def lossy(lines, nl, table, key, value):
            real(lines, nl, table, key, value)
            lines[:] = [[ln[0].replace("x = 1", "x = true"), ln[1]] for ln in lines]

        with mock.patch.object(codex_config, "_set_key", lossy), self.assertRaises(codex_config.MergeError) as ctx:
            codex_config.merge("[tui]\nx = 1\n", OWNED)
        self.assertIn("tui.x", str(ctx.exception))


class CheckTest(unittest.TestCase):
    def rows(self, text):
        return {r["name"]: r for r in codex_config.check(text, OWNED)}

    def test_check_reports_drift(self):
        merged = codex_config.merge("", OWNED)
        self.assertTrue(all(r["status"] == "ok" for r in self.rows(merged).values()))
        drifted = merged.replace('model = "gpt-6.1-sol"', 'model = "gpt-6-astra"')
        row = self.rows(drifted)["config model"]
        self.assertEqual((row["status"], row["actual"], row["expected"]), ("FAIL", '"gpt-6-astra"', '"gpt-6.1-sol"'))
        gone = merged.replace('theme = "clear"\n', "")
        row = self.rows(gone)["config tui.theme"]
        self.assertEqual((row["status"], row["actual"]), ("FAIL", "missing"))

    def test_check_does_not_confuse_false_with_zero(self):
        merged = codex_config.merge("", OWNED).replace("fast_mode = false", "fast_mode = 0")
        self.assertEqual(self.rows(merged)["config features.fast_mode"]["status"], "FAIL")


class ValueTest(unittest.TestCase):
    def test_toml_value(self):
        self.assertEqual(codex_config.toml_value('a"b\\c'), '"a\\"b\\\\c"')
        self.assertEqual(codex_config.toml_value(True), "true")
        self.assertEqual(codex_config.toml_value(False), "false")
        self.assertEqual(codex_config.toml_value(3), "3")
        self.assertEqual(codex_config.toml_value(["a", "b"]), '["a", "b"]')

    def test_template_is_the_decided_config(self):
        self.assertEqual(
            OWNED,
            {
                "": {
                    "model": "gpt-6.1-sol",
                    "model_reasoning_effort": "high",
                    "approval_policy": "never",
                    "sandbox_mode": "danger-full-access",
                },
                "features": {"fast_mode": False},
                "tui": {
                    "status_line": [
                        "project-name",
                        "git-branch",
                        "model-with-reasoning",
                        "context-used",
                        "five-hour-limit",
                        "weekly-limit",
                    ],
                    "status_line_use_colors": True,
                    "theme": "clear",
                },
            },
        )


class CliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.target = os.path.join(self.dir.name, "sub", "config.toml")
        self.template = os.path.join(ROOT, "config", "codex.toml")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-I", os.path.join(ROOT, "codex_config.py"), *args],
            capture_output=True,
            text=True,
        )

    def test_cli_merge_then_check(self):
        done = self.run_cli("merge", self.template, self.target)
        self.assertEqual(done.returncode, 0, done.stderr)
        done = self.run_cli("check", self.template, self.target)
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        rows = json.loads(lines[0])["rows"]
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(r["status"] == "ok" for r in rows))

    def test_cli_check_on_a_missing_file_fails_every_row(self):
        done = self.run_cli("check", self.template, self.target)
        self.assertEqual(done.returncode, 1)
        rows = json.loads(done.stdout)["rows"]
        self.assertEqual({r["actual"] for r in rows}, {"missing"})

    def test_cli_refusal_leaves_the_file_untouched(self):
        os.makedirs(os.path.dirname(self.target))
        raw = b'\xef\xbb\xbftui.theme = "x"\r\n'
        with open(self.target, "wb") as f:
            f.write(raw)
        done = self.run_cli("merge", self.template, self.target)
        self.assertEqual(done.returncode, 2)
        self.assertEqual(len(done.stderr.splitlines()), 1)
        self.assertTrue(done.stderr.startswith("codex_config: "))
        self.assertIn("tui.theme", done.stderr)
        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), raw)
        self.assertEqual(os.listdir(os.path.dirname(self.target)), ["config.toml"])

    def run_main(self, argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = codex_config.main(argv)
        return code, err.getvalue()

    def read_target(self):
        with open(self.target, "rb") as f:
            return f.read()

    def foreign_writer(self, contents):
        """merge() wrapper: after each merge the desktop app writes the next entry of contents."""
        real = codex_config.merge
        pending = list(contents)

        def merge(text, owned_keys):
            out = real(text, owned_keys)
            if pending:
                with open(self.target, "wb") as f:
                    f.write(pending.pop(0))
            return out

        return merge

    def test_concurrent_write_is_not_lost(self):
        os.makedirs(os.path.dirname(self.target))
        with open(self.target, "wb") as f:
            f.write(b"[desktop]\nx = 1\n")
        foreign = b"[desktop]\nx = 1\n[app]\nnew_key = 7\n"
        with mock.patch.object(codex_config, "merge", self.foreign_writer([foreign])):
            code, err = self.run_main(["merge", self.template, self.target])
        self.assertEqual((code, err), (0, ""))
        doc = tomllib.loads(self.read_target().decode("utf-8"))
        self.assertEqual(doc["app"], {"new_key": 7})
        self.assertEqual(doc["desktop"], {"x": 1})
        self.assertEqual(doc["model"], "gpt-6.1-sol")
        self.assertEqual(doc["tui"]["theme"], "clear")
        self.assertEqual(os.listdir(os.path.dirname(self.target)), ["config.toml"])

    def test_file_that_keeps_changing_exits_2_and_keeps_the_last_write(self):
        os.makedirs(os.path.dirname(self.target))
        with open(self.target, "wb") as f:
            f.write(b"[desktop]\nx = 1\n")
        writes = [f"[desktop]\nx = {n}\n".encode() for n in (2, 3, 4, 5)]
        with mock.patch.object(codex_config, "merge", self.foreign_writer(writes)):
            code, err = self.run_main(["merge", self.template, self.target])
        self.assertEqual(code, 2)
        self.assertEqual(err.strip(), "codex_config: config.toml kept changing during the merge")
        self.assertEqual(self.read_target(), writes[2])
        self.assertEqual(os.listdir(os.path.dirname(self.target)), ["config.toml"])

    def test_usage_error_exits_2(self):
        self.assertEqual(self.run_cli("bogus").returncode, 2)


if __name__ == "__main__":
    unittest.main()
