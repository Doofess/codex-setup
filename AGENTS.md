# codex-setup (this repo)

## What lives where
- Installed into Codex's homes by `install.ps1`: the rules, skills, agents and theme. Codex home is `$CODEX_HOME`, else `~/.codex`; skills go to `~/.agents/skills`.
- `config/codex.toml` holds the only keys of `config.toml` that are ours. `codex_config.py` merges them in and leaves every other byte alone, because the Codex desktop app writes the same file.

## Tests
- `python -m unittest discover -s tests -q`
- `ruff check .`

## Install
- Only from main, after merging: `pwsh -NoProfile -File install.ps1`.
- `install.ps1` must parse under Windows PowerShell 5.1.

## Flow
- Work in worktrees under `.codex/worktrees/` or `.claude/worktrees/`, open a PR, then `gh pr merge N --squash --delete-branch`.
- Leave the worktree directory before merging, or its removal fails.
