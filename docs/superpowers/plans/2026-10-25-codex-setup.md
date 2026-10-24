# codex-setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sibling of `Doofess/claude-setup` for OpenAI's Codex CLI: same rules, same look as far as Codex allows, installed and checked the same way. Plus a `codex` helper skill in claude-setup, so Claude sessions can hand work to Codex.

**Architecture:** New public repo `Doofess/codex-setup` at `C:\dev\codex-setup`. `install.ps1` (launched by `install.cmd` / `install.sh`) copies the rules, skills, agents and theme into Codex's homes. It merges only the keys we own into `~/.codex/config.toml` through `codex_config.py`, because the Codex desktop app writes the same file. `-Check -Json` reports rows the way claude-setup's does.

**Tech Stack:** PowerShell (must parse under Windows PowerShell 5.1), Python 3.13 stdlib (`tomllib`, `plistlib`, `unittest`), Codex CLI 0.163.0.

**Spec:** the design decisions are recorded in this plan's Decisions section below; there is no separate spec. Research the decisions rest on (two independent sources, Codex itself and a Sonnet agent, which agreed):
- `~/.codex/AGENTS.md` is the global rules file: 32768-byte budget, `AGENTS.override.md` wins.
- User skills live in `~/.agents/skills/<name>/SKILL.md` and are invoked as `$name`.
- Custom agents are `~/.codex/agents/<name>.toml`, with required keys `name`, `description` and `developer_instructions`, plus optional `model` and `model_reasoning_effort`. A custom `explorer` replaces the built-in one.
- The status line is the fixed id list `tui.status_line`; there is no script hook.
- `tui.theme` names a `.tmTheme` file in `~/.codex/themes/`. It colours syntax and diffs only.
- Never asking is `approval_policy = "never"` plus `sandbox_mode = "danger-full-access"`.
- Fast mode is turned off with `[features] fast_mode = false`.
- Superpowers 7.0.1 is installed as `superpowers@openai-curated-remote`.
- The desktop app owns `[desktop]`, `[plugins]`, `[marketplaces]`, `[mcp_servers.node_repl]`, `notify`, `[projects]` and `[windows]`.

## Decisions (from the user, 2026-10-25)

- Separate repo `codex-setup`, same layout and conventions as claude-setup. Terminal font, scheme and profiles stay owned by claude-setup.
- Codex never asks: `approval_policy = "never"`, `sandbox_mode = "danger-full-access"`.
- Main model `gpt-6.1-sol` at `high`. Escalation `gpt-6-astra` at `xhigh`, then `max`. `worker` agent: `gpt-6.1-sol` at `medium`. `explorer` agent: `gpt-6-luna` at `low`.
- Status line mirrors the Claude bar: `["project-name", "git-branch", "model-with-reasoning", "context-used", "five-hour-limit", "weekly-limit"]`, `status_line_use_colors = true`.
- Custom theme `clear.tmTheme`: diff tints dark red `#5F0000` / dark green `#005F00`, inline code `#3B78FF`, syntax from the terminal's current scheme (Campbell).
- Skills installed for Codex: `setup-check` (Codex version) and `claude` (hand tasks to `claude -p`). `underwater-photoshop` stays Claude-only.
- claude-setup gains a `codex` skill and a global rule for handing background tasks to Codex.

## Global Constraints

- `install.ps1` parses under Windows PowerShell 5.1 (`#Requires -Version 5.1`; no `` `e ``, no ternary, no `??`).
- Every file the scripts write is UTF-8 without BOM. Every PowerShell read names UTF-8 (`[IO.File]::ReadAllText($p, [Text.Encoding]::UTF8)`).
- Codex home is `$env:CODEX_HOME` when set, else `~/.codex`. The skills home is `~/.agents/skills`.
- Never replace `config.toml` wholesale. Only the keys in `config/codex.toml` are ours; every other byte of the file is preserved.
- Python is run as `python -I`. Tests: `python -m unittest discover -s tests -q`.
- Output colours as in claude-setup: 208 steps, 223 success, 228 warnings, 203 failures, 244 grey (xterm-256, `[char]27` escapes).
- Docs and comments follow claude-setup's voice: short, plain sentences, no marketing.

## Review Focus

1. `config.toml` already sets an owned key in another form: a root dotted key (`tui.theme = "x"`) or an inline table (`tui = {...}`). The merge must stop with an error naming the key and leave the file byte-identical, never write a file that defines the key twice. Test in Task 1.
2. `config.toml` with CRLF line endings, a UTF-8 BOM, no trailing newline, or a multi-line array value for an owned key (`status_line = [\n "a",\n]`). The merge preserves the endings and BOM state and replaces the whole multi-line value. Tests in Task 1.
3. The desktop app rewrites `config.toml` after an install and drops our keys. `-Check` must report each drifted key as FAIL, and a re-run of the install must repair it. Tests in Tasks 1 and 2.
4. `CODEX_HOME` points somewhere other than `~/.codex`: everything Codex-side goes there, nothing to `~/.codex`. Test in Task 2.
5. `codex` is not on PATH. `-Check` reports a FAIL row `codex` instead of throwing, and the install copies files and skips the plugin step with a warning. Test in Task 2.

---

### Task 1: Repo skeleton and the config merge (`codex_config.py`)

**Files:**
- Create: `.gitignore` (`__pycache__/`), `.gitattributes` (copy claude-setup's), `CLAUDE.md` (one line: `@AGENTS.md`), `AGENTS.md` (project instructions: what lives where, tests, install only from main after merging, worktrees under `.codex/worktrees/` or `.claude/worktrees/`, PR then `gh pr merge N --squash --delete-branch`)
- Create: `config/codex.toml`: the owned keys, exactly:
  ```toml
  model = "gpt-6.1-sol"
  model_reasoning_effort = "high"
  approval_policy = "never"
  sandbox_mode = "danger-full-access"

  [features]
  fast_mode = false

  [tui]
  status_line = ["project-name", "git-branch", "model-with-reasoning", "context-used", "five-hour-limit", "weekly-limit"]
  status_line_use_colors = true
  theme = "clear"
  ```
- Create: `codex_config.py`
- Test: `tests/test_codex_config.py`

**Interfaces:**
- Produces, for Task 2:
  - `python -I codex_config.py merge <template> <target>`: exit 0 with the file merged (written atomically via temp file plus `os.replace`; created when missing); exit 2 with one stderr line `codex_config: <reason>` and the file untouched when the merge is unsafe.
  - `python -I codex_config.py check <template> <target>`: prints one JSON line `{"rows": [{"name": "config <table.key>", "expected": "<toml>", "actual": "<toml or missing>", "status": "ok"|"FAIL"}]}`. Exit 0 when every row is ok, else 1.
- Python API: `owned(template_text: str) -> dict[str, dict[str, object]]` (table name, `""` for root, to keys); `merge(text: str, owned) -> str` (raises `MergeError`); `check(text: str, owned) -> list[dict]`; `toml_value(v) -> str` for str, bool, int and lists of str.

- [ ] **Step 1: Write the failing tests** in `tests/test_codex_config.py`:
  - `test_adds_keys_to_empty_file`: `merge("", owned(TEMPLATE))` parses with `tomllib`, and every owned value reads back equal.
  - `test_replaces_existing_values_and_keeps_everything_else`: input with root `model = "gpt-6-astra"`, `model_reasoning_effort = "high"`, `notify = ["x.exe", "turn-ended"]`, then `[tui]\nscreen_reader_detection_done = true`, then `[desktop]\nfollowUpQueueMode = "steer"`, then `[projects.'c:\dev\inwire']\ntrust_level = "trusted"`, each with a comment line. Assert `model == "gpt-6.1-sol"`, `tui.screen_reader_detection_done` is true, `desktop`, `projects` and `notify` are unchanged, and every comment line is still in the output.
  - `test_root_keys_go_before_the_first_table`: a new root key is inserted above the first `[table]` header, so TOML does not read it as part of that table.
  - `test_new_table_is_appended` (`[features]` absent) and `test_existing_table_gets_the_missing_key` (`[tui]` present without `theme`).
  - `test_subtable_header_is_not_the_table`: `[tui.notifications]` present and `[tui]` absent means a new `[tui]` is added and `[tui.notifications]` keeps its keys.
  - `test_multiline_array_is_replaced_whole`: `status_line = [\n  "git-branch",\n]` becomes the one-line owned value; the result parses.
  - `test_crlf_and_bom_are_preserved`: input `"\ufeffmodel = \"a\"\r\n[tui]\r\nx = 1"` (no final newline): the output starts with the BOM, every line ends in `\r\n` except the last, as in the input, and nothing else is added.
  - `test_dotted_root_key_is_refused`: `tui.theme = "x"` at the root raises `MergeError` naming `tui.theme`; the CLI exits 2 and the file's bytes are unchanged.
  - `test_inline_table_is_refused`: `tui = { theme = "x" }` raises `MergeError` the same way.
  - `test_invalid_input_is_refused`: input that `tomllib` rejects raises `MergeError` (`not valid TOML`) before any edit.
  - `test_check_reports_drift`: `check` on a merged file gives every row `ok`. After `model` is changed by hand, that row is `FAIL` with `actual` `"gpt-6-astra"`, and a removed key reads `missing`.
  - `test_cli_merge_then_check`: on a temp file, `merge` exits 0, then `check` exits 0 and prints one JSON line whose `rows` has one entry per owned key (8).
  - `test_template_is_the_decided_config`: `owned(read("config/codex.toml"))` equals the dict in this task's Files block.
- [ ] **Step 2: Run** `python -m unittest tests.test_codex_config -q`. Expected: FAIL (no module).
- [ ] **Step 3: Implement** `codex_config.py` as a line-based editor, not a TOML writer:
  - Find each table's region (header line `^\s*\[name\]\s*(#.*)?$` up to the next `^\s*\[`).
  - Within the region, a key's span runs from `^\s*key\s*=` to the line where its brackets balance, ignoring brackets inside strings.
  - Replace the span with `key = <toml_value>`, else insert the line after the region's last key line.
  - Refuse when `tomllib` shows the key's parent defined other than as a `[table]` header, i.e. a dotted root key or an inline table.
  - After editing, `tomllib.loads` the result and compare every owned value; on mismatch raise `MergeError`.
  - Keep the input's newline style, its BOM and its final-newline state.
- [ ] **Step 4: Run** the same command. Expected: `OK`.
- [ ] **Step 5: Commit** `codex_config.py: merge our keys into config.toml and leave the rest alone`.

### Task 2: Installer with `-Check -Json`

**Files:**
- Create: `install.ps1`, `install.cmd`, `install.sh`. The launchers are copied from claude-setup's, which are already generic.
- Test: `tests/test_install.py`, `tests/test_launchers.py` (port claude-setup's launcher test)

**Interfaces:**
- Consumes: Task 1's CLI.
- Produces: `install.ps1 [-SkipPlugins] [-Check] [-Json]`.
  - `-Json` with `-Check` prints one document, `{rows: [{name, expected, actual, status}], failures: [...]}`, and nothing else.
  - The install writes the state file `<codexHome>/codex-setup-state.json`: `{"repo": "<clone path>"}`, keeping every other key.
  - Row names are fixed for Task 4: `AGENTS.md`, `skill <name>`, `agent <name>`, `theme clear`, `config <table.key>` (from Task 1), `superpowers plugin`, `codex`.

- [ ] **Step 1: Write the failing tests.**
  - `test_parses_under_windows_powershell_51`: `powershell.exe -NoProfile -Command` with `[System.Management.Automation.Language.Parser]::ParseFile` reports 0 errors.
  - `test_install_into_a_temp_home`: run `install.cmd -SkipPlugins` with `USERPROFILE` and `HOME` set to a temp dir and `CODEX_HOME` unset. Then:
    - `<tmp>/.codex/AGENTS.md` equals `global/AGENTS.md`.
    - `<tmp>/.agents/skills/<name>/SKILL.md` exists for each folder in `skills/`.
    - `<tmp>/.codex/agents/<f>.toml` exists for each file in `agents/`.
    - `<tmp>/.codex/themes/clear.tmTheme` exists.
    - `config.toml` holds the owned keys.
    - The state file's `repo` is the repo root.
  - `test_install_keeps_desktop_keys`: pre-seed `<tmp>/.codex/config.toml` with a `[desktop]` table and `notify`; after the install both are byte-identical lines, and the old file is under `<tmp>/.codex/backups/codex-setup-<stamp>/config.toml`.
  - `test_codex_home_is_respected`: with `CODEX_HOME=<tmp>/ch`, the Codex files land in `<tmp>/ch` and `<tmp>/.codex` is not created.
  - `test_check_json_after_install_passes`: `install.cmd -Check -Json -SkipPlugins` exits 0, its stdout is a single JSON document, and every row is `ok` except `superpowers plugin` and `codex`, which read `skipped`.
  - `test_check_reports_config_drift`: after the install, set `model = "x"` by hand. `-Check -Json` exits 1, the row `config model` is `FAIL`, and `failures` names it. Re-running the install makes `-Check` exit 0 again.
  - `test_check_without_codex_on_path`: with `PATH` stripped of the Codex bin folder, `-Check -Json` (no `-SkipPlugins`) gives row `codex` status `FAIL` with actual `not on PATH`, and does not throw.
  - `test_merge_refusal_fails_the_install`: seed the root dotted key `tui.theme = "x"`. The install exits 1, names `tui.theme`, and leaves `config.toml` unchanged.
- [ ] **Step 2: Run** `python -m unittest tests.test_install tests.test_launchers -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `install.ps1` with the same structure, helpers and voice as claude-setup's: `Write-Color`/`Write-Step`, `Read-Utf8`/`Write-Utf8NoBom`, `Set-StateRepo`, `Add-SameRow`. The `.DESCRIPTION` numbered list says what it does:
  1. Backs up `AGENTS.md`, `config.toml`, our skills, agents and theme into `<codexHome>/backups/codex-setup-<stamp>/`.
  2. Copies `global/AGENTS.md`, `skills/*`, `agents/*.toml` and `themes/*.tmTheme`.
  3. Merges `config/codex.toml` via `python -I codex_config.py merge`; exit 2 means fail with its stderr line.
  4. Unless `-SkipPlugins`: if `codex plugin list` lacks an enabled `superpowers` row, runs `codex plugin add superpowers@openai-curated-remote`.
  5. Prints the check table.
  6. Runs `codex doctor` and shows its summary lines without failing on them; it warns about `node_repl` outside the desktop app.
  Under `-Check` nothing is written.
- [ ] **Step 4: Run** the tests. Expected: `OK`.
- [ ] **Step 5: Commit** `install.ps1: copy, merge and check the Codex setup`.

### Task 3: Rules, agents, theme and MCP presets

**Files:**
- Create: `global/AGENTS.md`, `agents/worker.toml`, `agents/explorer.toml`, `themes/clear.tmTheme`, `mcp-presets/README.md`, `mcp-presets/web.toml`, `mcp-presets/cluster.toml`
- Test: `tests/test_content.py`

**Interfaces:**
- Produces: the files Task 2 copies. Agent names are `worker` and `explorer`; the theme name is `clear`.

- [ ] **Step 1: Write the failing tests.**
  - `test_rules_fit_codex_budget`: `global/AGENTS.md` is under 8192 bytes, well inside Codex's 32768.
  - `test_rules_name_the_decided_models`: the file contains `gpt-6.1-sol`, `gpt-6-astra`, `worker`, `explorer`, `$claude`, `$setup-check` and `C:/dev/codex-setup`.
  - `test_rules_have_no_claude_only_words`: none of `advisor`, `Opus`, `Sonnet`, `Haiku`, `Fable`, `/effort`, `CLAUDE.md`, `.mcp.json`, `install.ps1 -SkipPlugins` appear.
  - `test_agents`: each `agents/*.toml` parses. `worker` is `{model: "gpt-6.1-sol", model_reasoning_effort: "medium"}` and `explorer` is `{model: "gpt-6-luna", model_reasoning_effort: "low"}`, each with a non-empty `name` equal to its file stem, plus `description` and `developer_instructions`.
  - `test_explorer_says_read_only`: its `developer_instructions` contain "read-only" and "do not edit"; Codex can't enforce this per agent, so the instruction carries it.
  - `test_theme`: `plistlib.loads` parses `themes/clear.tmTheme`, its `name` is `clear`, the setting for scope `markup.inserted` (and `diff.inserted`) has `background` `#005F00`, `markup.deleted` and `diff.deleted` have `#5F0000`, and `markup.inline.raw` or `markup.raw.inline` has `foreground` `#3B78FF`.
  - `test_presets_parse`: each `mcp-presets/*.toml` parses and every key sits under `mcp_servers`. They hold the same servers as claude-setup's `mcp-presets/*.mcp.json`, with `${VAR}` secrets moved to `env_vars`.
- [ ] **Step 2: Run** `python -m unittest tests.test_content -q`. Expected: FAIL.
- [ ] **Step 3: Write the content.**
  - `global/AGENTS.md` ports `claude-setup/global/CLAUDE.md` section by section into Codex terms:
    - Planning questions go through Codex's question tool in Plan mode; verify its name in Step 4.
    - The superpowers workflow is unchanged, still without `brainstorming`.
    - Delegation goes to `worker`/`explorer` with the model rules above.
    - Escalation is `/model` to gpt-6-astra xhigh, then max.
    - Context hygiene: `/new` between tasks, small outputs.
    - Photo edits stay in Claude Code.
    - Defaults are unchanged, except that project MCP servers go in the repo's `.codex/config.toml`, starting from `mcp-presets/`, and the project must be trusted.
    - Setup changes go in `C:/dev/codex-setup`, then `install.ps1`, then `$setup-check`.
    - The `$claude` skill is for second opinions.
  - Agent TOMLs: worker's instructions match claude-setup's `agents/worker.md`; explorer's match `agents/Explore.md`.
  - Theme: syntax colours from Campbell (`#0C0C0C` background, `#CCCCCC` foreground, `#C50F1F` red, `#13A10E` green, `#C19C00` yellow, `#3B78FF` bright blue, `#881798` purple, `#3A96DD` cyan, `#767676` comments).
- [ ] **Step 4: Ask Codex to review the rules for Codex idioms.** Run `codex exec -s read-only --skip-git-repo-check --ephemeral -C <worktree> -o <scratch>/rules-review.md` with a brief asking whether every tool, command, skill and key named in `global/AGENTS.md` and `agents/*.toml` exists in 0.163, and what the Plan-mode question tool is called. Apply each finding only after checking it against `codex --help` or the binary. Rerun the tests.
- [ ] **Step 5: Commit** `Rules, agents, theme and MCP presets for Codex`.

### Task 4: Codex skills `setup-check` and `claude`

**Files:**
- Create: `skills/setup-check/SKILL.md`, `skills/claude/SKILL.md`
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: Task 2's state file `codex-setup-state.json`, `install.cmd -Check -Json`, and the row names.

- [ ] **Step 1: Write the failing tests.**
  - `test_frontmatter`: each SKILL.md starts with `---`, has `name:` equal to its folder and a `description:` starting with `Use when`, and is under 80 lines.
  - `test_setup_check_steps`: the body names `codex-setup-state.json`, `install.cmd -Check -Json`, `codex doctor` and `git -C <repo> branch --show-current`, and says to run `install.cmd` only from the main checkout.
  - `test_claude_skill_commands`: the body has a `claude -p` command reading the brief from stdin, a read-only variant, the instruction to verify Claude's claims before acting, and the scratch-file pattern for its answer.
- [ ] **Step 2: Run** `python -m unittest tests.test_skills -q`. Expected: FAIL.
- [ ] **Step 3: Write the skills.**
  - `setup-check` mirrors claude-setup's: find the clone, check it is main and fresh, run `-Check`, repair once with `install.cmd`, hand over what the installer can't fix (`codex login`, `gh auth login`), done only when `-Check` exits 0.
  - `claude`: write the brief to a file, run `claude -p` in the background with the model chosen for the job, read the answer file, verify before acting. Confirm the flags with `claude --help` (permission mode / allowed tools for read-only).
- [ ] **Step 4: Run** the tests. Expected: `OK`.
- [ ] **Step 5: Commit** `Skills: setup-check and claude for Codex`.

### Task 5: README, publish, install and live check

**Files:**
- Create: `README.md` in claude-setup's shape: what you see (status line, theme), set up a new machine, check a machine, changing something, reference (what goes where), the gaps (no script status line, no session cards, no advisor, no per-model effort).

- [ ] **Step 1:** Write the README. Commit `README`.
- [ ] **Step 2:** Create the GitHub repo and push main (public, like claude-setup): `gh repo create Doofess/codex-setup --public --source . --push`. Then open the feature branch's PR, merge with `gh pr merge N --squash --delete-branch`, and pull main.
- [ ] **Step 3:** From main: `pwsh -NoProfile -File install.ps1`, then `install.cmd -Check`. Expected: exit 0. Quote the table.
- [ ] **Step 4:** Live look. Start `codex` in a separate Windows Terminal window in `C:\dev\codex-setup`. Capture it with PrintWindow (the method in the `demo-session-screenshots` memory) and check:
  - The status line shows the six items.
  - Asking for a one-line change shows the dark diff tints.
  Show the user the screenshot.

### Task 6 (claude-setup repo): the `codex` skill and rule

**Files:**
- Create: `skills/codex/SKILL.md`
- Modify: `global/CLAUDE.md` (one line under "Models and usage")
- Test: `tests/test_install.py` (new `CodexSkillStaticTest`)

- [ ] **Step 1: Write the failing test.** The frontmatter `name: codex` has a `description` starting with `Use when`. The body contains:
  - `codex exec -s read-only --skip-git-repo-check --ephemeral`
  - `-o` together with "scratchpad"
  - `run_in_background`
  - "verify"
  - the edit variant, which runs only in a worktree
  The file is under 80 lines. `global/CLAUDE.md` mentions the `codex` skill.
- [ ] **Step 2: Run** `python -m unittest tests.test_install -q`. Expected: FAIL.
- [ ] **Step 3: Write the skill.**
  - Brief to a file.
  - Run it in the background as `codex exec ... -C <dir> -o <scratch>/answer.md - < brief.md`.
  - Default sandbox `read-only`. Edits only in a worktree with `-s workspace-write`.
  - Use it for questions about Codex itself, independent research and second opinions; it runs on the OpenAI subscription.
  - Verify claims before acting.
  - The rule line goes in `global/CLAUDE.md`.
- [ ] **Step 4: Run** the full suite. Expected: OK. Then PR, merge, and `install.ps1` from main.
