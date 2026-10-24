# Global rules

## Planning and design
- Planning or any non-trivial change: in Plan mode (`/plan`), ask the open design questions through the `request_user_input` tool, one to three per call, each with two or three exclusive options, the recommended one first and its label suffixed `(Recommended)`; never as numbered questions in chat. Don't call Superpowers' `brainstorming`.
- Reviewing a diff: the built-in `/review`.

## superpowers: execution
- Turning an agreed design into steps: `writing-plans`, then `executing-plans` by default. Under it, dispatch each plan task that edits more than a couple of files to `worker` with the task's brief, then check its report and run the tests yourself; do small tasks inline. Use `subagent-driven-development` only for a plan too long for one context; its implementers are `worker`.
- Feature work: `using-git-worktrees` for isolation.
- Bugs and failures: `systematic-debugging`.
- Before saying done, fixed or passing: run the check (tests, build, the command itself) in this turn and quote the relevant output.

## Models and usage
- Sessions run on gpt-6.1-sol at high effort. For the hardest problems, `/model` to gpt-6-astra at xhigh, then max if still stuck. Pick the model at session start rather than switching mid-session.
- Delegate whenever the work means reading or editing more than a couple of files, and name the agent when you spawn it: `explorer` (gpt-6-luna, low, read-only) for search and reading files; `worker` (gpt-6.1-sol, medium) for implementation; `worker_high` (gpt-6.1-sol, high) instead for concurrency, parsers, security, or after a failed first attempt.
- Web research goes to `worker`; check its findings before acting on them. Review a whole branch yourself on gpt-6-astra.
- For a second opinion or a background task from Claude Code, use the `$claude` skill.

## Context hygiene
- One task per session; `/new` between unrelated tasks.
- Keep command output small: `tail`, `grep` or quiet flags, print only test failures.
- Read large docs (`PLAN.md`, specs) by heading, with a line range, never whole.
- In Playwright prefer `browser_evaluate` returning a small JSON value over screenshots and snapshots; screenshot only when judging the look.

## Compact instructions
When compacting, keep decisions, file paths, open todos and failing test names.

## Photo editing (paid work)
- Underwater or macro photo edits, ARW/RAW, Camera Raw, backscatter, "pop", PSD deliverables stay in Claude Code (`underwater-photoshop` skill). Don't start them here.

## Defaults
- Issue tracker: GitHub Issues via `gh`. Docs, specs, ADRs: `docs/` in the repo.
- Git: run `push` and other history-changing commands yourself when I ask for them; don't hand the command back to me. Confirm first only for what can't be undone (`push --force` to a shared branch, `reset --hard`, `clean -f`, `branch -D`).
- Styles in any form (CSS, Tailwind, StyleX, inline): `frontend-design` decides the look. When the `good-css` plugin is installed, read its skill before writing the declarations.
- MCP servers for one project go in that repo's `.codex/config.toml` (start from `mcp-presets/` in the setup repo), never in user config. The project must be trusted for Codex to load it.
- Setup lives in `C:/dev/codex-setup` (repo `Doofess/codex-setup`); change config there and run `install.ps1`, so the desktop stays identical.
- After install.ps1 or on a new PC: `$setup-check`.
