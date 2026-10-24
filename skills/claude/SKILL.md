---
name: claude
description: Use when a question is about Claude Code itself, when independent research or a second opinion would help, or when the user asks to give Claude a task. Hands the task to Claude Code (`claude -p`) in the background.
---

# Hand a task to Claude Code

Claude Code is installed on this PC and signed in to the user's Claude subscription, with the user's own setup
(claude-setup). It runs while you keep working. Its answer is a lead, not evidence: verify before acting on it.

## Good tasks

- Questions about Claude Code itself or about claude-setup (`C:\dev\claude-setup`).
- Independent research, in parallel with your own: where the two answers disagree is where to look.
- A second opinion on a plan, a diff or a bug theory. Give it the files, not your conclusion.
- Never photo edits: those are the user's paid work and run in their own Claude Code session.

## How

1. **Brief.** Write the brief to a file in a scratch folder outside the repo (for example `$env:TEMP\claude-task\`):
   the goal, what is ruled out, the files to read, the output wanted (format and length), and "mark anything you
   could not verify as UNVERIFIED".
2. **Run** it in the background, read-only, from the folder it should look at:

   ```powershell
   Start-Process -WindowStyle Hidden cmd -ArgumentList '/c', 'claude -p --model sonnet --permission-mode dontAsk --allowedTools Read Grep Glob WebSearch WebFetch --no-session-persistence < "%TEMP%\claude-task\brief.md" > "%TEMP%\claude-task\claude-answer.md" 2>&1'
   ```

   PowerShell has no `<` redirection, hence `cmd /c`. In Git Bash: `claude -p ... < "<scratch>/brief.md" >
   "<scratch>/claude-answer.md" 2>&1 &`.
   - `--permission-mode dontAsk --allowedTools Read Grep Glob WebSearch WebFetch`: it can read and search, and
     every other tool (edits, shell) is refused. Always pass it: the user's Claude settings bypass permissions by
     default.
   - `--model opus` for the hardest questions or a whole-branch review; `sonnet` otherwise; `haiku` for a quick
     lookup.
3. **Read** `claude-answer.md` once the process has exited. Check now and then rather than waiting in a loop.
4. **Verify** each claim you will act on: the files it names, `<command> --help`, or a test. Tell the user which
   parts you checked.

## Edits

Only in a git worktree you made for the task: run it from there with `--permission-mode acceptEdits` instead of
the read-only flags. Review its diff and run the tests yourself before anything leaves the worktree.
