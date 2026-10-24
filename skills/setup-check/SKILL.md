---
name: setup-check
description: Use when setting up this Codex configuration on a PC, after install.ps1, when Codex looks or behaves differently than the setup says, or when the user asks whether the setup is right.
---

# Prove and repair the setup

Proves the Codex setup on this PC matches the repo, and repairs what drifted. Run every command in PowerShell
(`<repo>` is the clone path, with backslashes). Never edit the repo's files from this skill: drift on the machine is
fixed by the installer, not by editing the repo. The Codex desktop app rewrites `config.toml`, so a key we own can
drift without anyone touching the setup.

1. **Find the clone.** Read `repo` from the state file in the Codex home (`$env:CODEX_HOME`, else `~\.codex`):
   `(Get-Content (Join-Path ($env:CODEX_HOME, "$HOME\.codex" | Where-Object { $_ } | Select-Object -First 1) 'codex-setup-state.json') -Raw | ConvertFrom-Json).repo`.
   If the file or the key is missing, ask the user for the clone path (the installer records it on its next run).
2. **Check it is the main checkout.** Both must hold, else stop and ask for the main clone:
   - `git -C <repo> rev-parse --git-dir` prints the same as `git -C <repo> rev-parse --git-common-dir`
   - `git -C <repo> branch --show-current` prints `main`
3. **Fresh?** Run `git -C <repo> fetch -q`, then `git -C <repo> status -sb`. If main is behind, say so and run
   `git -C <repo> pull --ff-only` only after the user says yes.
4. **Prove.** Run `& "<repo>\install.cmd" -Check -Json` (quoted: the path may hold spaces) with a long timeout: it
   runs `codex` itself and can take a minute. It prints one JSON document, `{rows, failures}`, and exits 1 when a
   row is `FAIL`. Quote the failing rows as `name: expected / actual`. Then run `codex doctor` and quote any line
   it marks as an error. Its `node_repl` warning is expected outside the desktop app; ignore it.
5. **Repair.** For any FAIL, run `& "<repo>\install.cmd"` once, with the same long timeout, then step 4 again. If
   rows still fail after one repair, show them and stop; do not loop.
6. **Hand over what the installer can't fix.** Name the row and give the exact command:

   | Row or message | Tell the user |
   |---|---|
   | `codex`: not on PATH | Codex CLI is missing or off PATH. Reinstall it, open a new terminal, then step 5. |
   | Install stops with `codex_config: ...` naming a key | `config.toml` sets that key in a form the merge won't edit (a dotted key or an inline table). Show the line; with the user's yes, move it under its `[table]` header, then step 5. |
   | Codex not signed in (`codex doctor`) | `codex login` |
   | GitHub CLI not signed in | `gh auth login` |

7. **Done only when step 4 exits 0 on the main checkout.** Quote its result: every row `ok` or `skipped`.
   Codex reads `config.toml`, `AGENTS.md`, skills and agents when it starts, so tell the user to start a new
   `codex` process if step 5 ran.
