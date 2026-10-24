# codex-setup

The Codex CLI side of [claude-setup](https://github.com/Doofess/claude-setup): the same rules and the same way of
working, in Codex's own files. One script installs it, checks it and repairs it, on any PC.

## What you see

### The status line

Codex's footer, in the same order as the Claude bar:

- **Where you are**: the project and the branch.
- **Who is working**: the model with its reasoning effort.
- **How full the context is**, then the **5-hour** and **weekly** plan limits.

Codex draws these items itself from a fixed list (`tui.status_line`); it can't run a script, so there are no custom
colours, icons or overflow onto a second line as in the Claude bar.

### The theme

`clear` colours syntax and diffs: added lines on dark green `#005F00`, removed lines on dark red `#5F0000`, inline
code in blue `#3B78FF`, and syntax in the terminal's Campbell colours. Everything else on screen is the terminal's
own scheme, which claude-setup sets.

### Behind the scenes

- **Rules**: `global/AGENTS.md` becomes `~/.codex/AGENTS.md`, the port of claude-setup's global `CLAUDE.md`: plan with
  questions in Plan mode, superpowers' `writing-plans` and `executing-plans`, delegate to agents, verify before
  saying done.
- **Models**: `gpt-6.1-sol` at high effort; `/model` to `gpt-6-astra` at xhigh, then max, for the hardest problems.
- **Two agents**: `worker` (`gpt-6.1-sol`, medium, implementation briefs) and `explorer` (`gpt-6-luna`, low,
  read-only search; replaces the built-in one).
- **No prompts**: `approval_policy = "never"` and `sandbox_mode = "danger-full-access"`, as claude-setup's bypass
  mode. The rules still ask before what can't be undone.
- **Fast mode off**, as in Claude Code.
- **Skills**: `$setup-check` proves and repairs this setup; `$claude` hands a task to Claude Code (`claude -p`,
  read-only) for a second opinion. Claude's side has the mirror, the `codex` skill in claude-setup.
- **Plugins**: superpowers (`superpowers@openai-curated-remote`), installed when missing.

## Set up a new machine (Windows)

1. Install Codex CLI and sign in: `codex login`.
2. Python 3.11 or later on PATH (the config merge uses `tomllib`).
3. Clone to `C:\dev\codex-setup`, then from main, in any shell: `install.cmd` (`./install.sh` in Git Bash).
4. Start a new `codex`.

The installer backs up what it replaces to `~/.codex/backups/codex-setup-<stamp>/` first, and is safe to re-run.

| Flag | Does |
|---|---|
| `-SkipPlugins` | Skips every step that calls `codex` (plugin, `codex doctor`, the version row); their rows read `skipped`. |
| `-Check` | Runs only the checks; nothing changes. Exits 1 when a row fails. |
| `-Json` | With `-Check`, prints one JSON document `{rows, failures}` and nothing else. |

### Check a machine

Run `$setup-check` in Codex. It finds the clone through `~/.codex/codex-setup-state.json`, checks the clone is main
and up to date, runs `install.cmd -Check -Json` and `codex doctor`, repairs once with the installer, and names what
only you can fix (`codex login`, `gh auth login`).

## Changing something

Change it here, never in `~/.codex` directly: a worktree, a PR, `gh pr merge N --squash --delete-branch`, then
`install.cmd` from main. The tests: `python -m unittest discover -s tests -q`.

## Reference

### What goes where

| Repo | Machine |
|---|---|
| `global/AGENTS.md` | `~/.codex/AGENTS.md` |
| `config/codex.toml` | merged into `~/.codex/config.toml` |
| `agents/*.toml` | `~/.codex/agents/` |
| `themes/*.tmTheme` | `~/.codex/themes/` |
| `skills/*/` | `~/.agents/skills/` |
| `mcp-presets/*.toml` | nothing; copy into a project's `.codex/config.toml` (see [its README](mcp-presets/README.md)) |

`~/.codex` is `$CODEX_HOME` when that is set.

### config.toml merge rules

The Codex desktop app writes the same `config.toml` (its `[desktop]`, `[plugins]`, `[marketplaces]`, `notify`,
`[projects]`, `[windows]` and MCP servers). `codex_config.py` changes only the keys in `config/codex.toml`, line by
line, and keeps every other byte: comments, order, line endings. When the file sets one of our keys in a form it
won't edit safely (a dotted key such as `tui.theme = ...` at the top, or an inline table), it stops and changes
nothing; move that line under its `[table]` header and run the install again. When the desktop app drops one of our
keys, `-Check` shows the row as FAIL and the next install puts it back.

### What claude-setup has and Codex can't

- A script-driven status bar (colours per model, overflow onto the hint line) and the session-cards mod: Codex has
  no UI mods.
- The advisor, and effort settings per model.
- Per-agent tool limits: `explorer` is read-only by instruction, not by sandbox.
- The Claude Code theme: Codex themes colour syntax and diffs only.
