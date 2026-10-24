#Requires -Version 5.1
<#
.SYNOPSIS
  Applies this repo's Codex config to the current machine. Safe to re-run.

.DESCRIPTION
  1. Backs up ~/.codex/{AGENTS.md,config.toml}, and the skills, agents and theme this repo owns, to
     ~/.codex/backups/codex-setup-<stamp>/
  2. Copies global/AGENTS.md, skills/* (to ~/.agents/skills), agents/*.toml and themes/*.tmTheme into ~/.codex
  3. Merges config/codex.toml into config.toml with `python -I codex_config.py merge`: only our keys change, every
     other byte survives. A merge that refuses (exit 2) fails the install with its message and leaves config.toml alone
  4. Unless -SkipPlugins: when `codex plugin list` has no enabled superpowers row, runs
     `codex plugin add superpowers@openai-curated-remote`
  5. Prints the check table (every file and config key above, the plugin, the codex CLI) and fails when a row is FAIL
  6. Runs `codex doctor` and shows its summary lines without failing on them; warns about node_repl, a desktop-app
     tool the CLI doesn't have

  The Codex home is $env:CODEX_HOME when set, else ~/.codex. Skills go to ~/.agents/skills.

.PARAMETER SkipPlugins
  Skip every step that calls the codex CLI (plugin check and install, codex doctor, the version row). Their rows read `skipped`.

.PARAMETER Check
  Run only the checks: nothing is backed up, copied, merged or installed, and no file changes. Exits 1 when a check fails.

.PARAMETER Json
  With -Check, print one JSON document {rows: [{name, expected, actual, status}], failures: [...]} to stdout and
  nothing else.

#>
[CmdletBinding()]
param([switch]$SkipPlugins, [switch]$Check, [switch]$Json)

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$codexDir = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
$skillsDir = Join-Path $HOME '.agents\skills'
$statePath = Join-Path $codexDir 'codex-setup-state.json'
$configPath = Join-Path $codexDir 'config.toml'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $codexDir "backups\codex-setup-$stamp"
$failures = @()
$quiet = [bool]$Json   # -Json: stdout carries the JSON document only, so nothing else is written to the host

# Output colours come from the repo's two palettes, orange and grey (xterm-256 indices):
# 208 orange for steps, 223 peach for success, 228 yellow for warnings, 203 red for failures, 244 grey.
# The 16 Write-Host console colours have no orange, so these are ANSI escapes ([char]27: `e needs PS 6+).
function Write-Color($msg, [int]$color) { if ($quiet) { return }; Write-Host "$([char]27)[38;5;${color}m$msg$([char]27)[0m" }
function Write-Step($msg) { Write-Color "==> $msg" 208 }
# Windows PowerShell 5.1's Get-Content reads a BOM-less file in the ANSI code page (1252 on most PCs), which garbles
# any non-ASCII value, so every read names UTF-8.
function Read-Utf8($path) { [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) }
function Write-Utf8NoBom($path, $text) {
  [IO.File]::WriteAllText($path, $text, [Text.UTF8Encoding]::new($false))
}

function Set-StateRepo([string]$statePath, [string]$repoDir) {
  # Records the clone in the state file (/setup-check reads it). Keeps every other key; writes only on change.
  $state = $null
  if (Test-Path $statePath) { $state = Read-Utf8 $statePath | ConvertFrom-Json }
  if ($null -eq $state) { $state = [pscustomobject]@{} }
  if ($state.PSObject.Properties['repo'] -and $state.repo -ceq $repoDir) { return }
  $state | Add-Member -NotePropertyName repo -NotePropertyValue $repoDir -Force
  Write-Utf8NoBom $statePath (($state | ConvertTo-Json -Depth 20) + "`n")
}

# Runs a program and returns its exit code and combined output. Windows PowerShell 5.1 turns a native program's stderr
# into error records, which -ErrorAction Stop would throw on, so the call runs under Continue.
function Invoke-Native([string]$exe, [string[]]$arguments) {
  $prev = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $lines = @(& $exe @arguments 2>&1 | ForEach-Object { "$_" })
    $code = $LASTEXITCODE
  } finally { $ErrorActionPreference = $prev }
  [pscustomobject]@{ Code = $code; Out = (($lines | Out-String).TrimEnd()); Lines = $lines }
}

function Get-FileSha([string]$path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash }
function Test-SameFile([string]$a, [string]$b) { (Test-Path -LiteralPath $b) -and (Test-Path -LiteralPath $a) -and (Get-FileSha $a) -eq (Get-FileSha $b) }
# True when every file under $src is in $dst with the same bytes.
function Test-SameTree([string]$src, [string]$dst) {
  foreach ($f in (Get-ChildItem -LiteralPath $src -Recurse -File)) {
    $rel = $f.FullName.Substring($src.TrimEnd('\').Length + 1)
    if (-not (Test-SameFile $f.FullName (Join-Path $dst $rel))) { return $false }
  }
  return $true
}

function Copy-ToDir([string]$src, [string]$dstDir) {
  New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
  Copy-Item -LiteralPath $src -Destination $dstDir -Force
}

function Add-BackupItem([string]$path, [string]$rel) {
  if (-not (Test-Path -LiteralPath $path)) { return }
  $dst = Join-Path $backup $rel
  New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
  Copy-Item -LiteralPath $path -Destination $dst -Recurse -Force
}

# What the repo installs.
$skillSrc = @()
if (Test-Path (Join-Path $repo 'skills')) {
  $skillSrc = @(Get-ChildItem -LiteralPath (Join-Path $repo 'skills') -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') })
}
$agentSrc = @()
if (Test-Path (Join-Path $repo 'agents')) { $agentSrc = @(Get-ChildItem -LiteralPath (Join-Path $repo 'agents') -Filter '*.toml' -File) }
$themeSrc = @()
if (Test-Path (Join-Path $repo 'themes')) { $themeSrc = @(Get-ChildItem -LiteralPath (Join-Path $repo 'themes') -Filter '*.tmTheme' -File) }
$agentsMd = Join-Path $repo 'global\AGENTS.md'
$template = Join-Path $repo 'config\codex.toml'
$codexCmd = Get-Command codex -ErrorAction SilentlyContinue | Select-Object -First 1
$env:PYTHONIOENCODING = 'utf-8'

if (-not $Check) {
  Write-Step "Backup to $backup"
  Add-BackupItem (Join-Path $codexDir 'AGENTS.md') 'AGENTS.md'
  Add-BackupItem $configPath 'config.toml'
  foreach ($s in $skillSrc) { Add-BackupItem (Join-Path $skillsDir $s.Name) "skills\$($s.Name)" }
  foreach ($a in $agentSrc) { Add-BackupItem (Join-Path $codexDir "agents\$($a.Name)") "agents\$($a.Name)" }
  foreach ($t in $themeSrc) { Add-BackupItem (Join-Path $codexDir "themes\$($t.Name)") "themes\$($t.Name)" }

  Write-Step 'Copy AGENTS.md, skills, agents and themes'
  Copy-ToDir $agentsMd $codexDir
  foreach ($s in $skillSrc) {
    $dst = Join-Path $skillsDir $s.Name
    if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }   # a file dropped from the repo goes too
    New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null
    Copy-Item -LiteralPath $s.FullName -Destination $dst -Recurse -Force
  }
  foreach ($a in $agentSrc) { Copy-ToDir $a.FullName (Join-Path $codexDir 'agents') }
  foreach ($t in $themeSrc) { Copy-ToDir $t.FullName (Join-Path $codexDir 'themes') }
  Set-StateRepo $statePath $repo

  Write-Step 'Merge config.toml'
  $merge = Invoke-Native 'python' @('-I', (Join-Path $repo 'codex_config.py'), 'merge', $template, $configPath)
  if ($merge.Code -ne 0) {
    $reason = if ($merge.Out) { $merge.Out } else { "codex_config.py merge exited $($merge.Code)" }
    $failures += "config.toml: $reason"
    Write-Color "    $reason" 203
  }
}

# ---- codex CLI: plugin and version ----
$pluginState = 'skipped'; $codexState = 'skipped'
function Get-SuperpowersState {
  # `codex plugin list` prints one line per plugin, e.g. `name@marketplace   installed, enabled   version   source`.
  $r = Invoke-Native 'codex' @('plugin', 'list')
  if ($r.Code -ne 0) { return 'plugin list failed' }
  foreach ($l in $r.Lines) { if ($l -match 'superpowers' -and $l -match '\benabled\b') { return 'enabled' } }
  return 'not enabled'
}
if (-not $SkipPlugins) {
  Write-Step 'Plugins'
  if (-not $codexCmd) {
    $pluginState = 'codex not on PATH'; $codexState = 'not on PATH'
    Write-Color '    codex is not on PATH: skipping the plugin step' 228
  } else {
    $codexState = [regex]::Match((Invoke-Native 'codex' @('--version')).Out, '\d+\.\d+\.\d+').Value
    if (-not $codexState) { $codexState = 'unknown' }
    $pluginState = Get-SuperpowersState
    if ($pluginState -ne 'enabled' -and -not $Check) {
      Write-Color '    superpowers is not enabled: adding it' 228
      $add = Invoke-Native 'codex' @('plugin', 'add', 'superpowers@openai-curated-remote')
      if ($add.Code -ne 0) { Write-Color "    codex plugin add failed: $($add.Out)" 203 }
      $pluginState = Get-SuperpowersState
    }
  }
}

# ---- check table ----
Write-Step 'Check'
$rows = @()
function Add-Row([string]$name, [string]$expected, [string]$actual, [bool]$ok, [bool]$skipped = $false) {
  $status = if ($skipped) { 'skipped' } elseif ($ok) { 'ok' } else { 'FAIL' }
  $script:rows += [pscustomobject]@{ Name = $name; Expected = $expected; Actual = $actual; Status = $status }
}
function Add-FileRow([string]$name, [string]$src, [string]$dst) {
  $same = Test-SameFile $src $dst
  Add-Row $name 'same as repo' $(if ($same) { 'same as repo' } elseif (Test-Path -LiteralPath $dst) { 'differs' } else { 'missing' }) $same
}
Add-FileRow 'AGENTS.md' $agentsMd (Join-Path $codexDir 'AGENTS.md')
foreach ($s in $skillSrc) {
  $dst = Join-Path $skillsDir $s.Name
  $same = (Test-Path -LiteralPath $dst) -and (Test-SameTree $s.FullName $dst)
  Add-Row "skill $($s.Name)" 'same as repo' $(if ($same) { 'same as repo' } elseif (Test-Path -LiteralPath $dst) { 'differs' } else { 'missing' }) $same
}
foreach ($a in $agentSrc) { Add-FileRow "agent $($a.BaseName)" $a.FullName (Join-Path $codexDir "agents\$($a.Name)") }
foreach ($t in $themeSrc) { Add-FileRow "theme $($t.BaseName)" $t.FullName (Join-Path $codexDir "themes\$($t.Name)") }

$cfg = Invoke-Native 'python' @('-I', (Join-Path $repo 'codex_config.py'), 'check', $template, $configPath)
$cfgDoc = $null
try { $cfgDoc = $cfg.Out | ConvertFrom-Json } catch { }
if ($cfgDoc -and $cfgDoc.PSObject.Properties['rows']) {
  foreach ($r in @($cfgDoc.rows)) { Add-Row ([string]$r.name) ([string]$r.expected) ([string]$r.actual) ($r.status -eq 'ok') }
} else {
  Add-Row 'config' 'codex_config.py check' $(if ($cfg.Out) { $cfg.Out } else { "exit $($cfg.Code)" }) $false
}

Add-Row 'superpowers plugin' 'enabled' $(if ($SkipPlugins) { 'skipped' } else { $pluginState }) ($pluginState -eq 'enabled') ([bool]$SkipPlugins)
Add-Row 'codex' 'on PATH' $(if ($SkipPlugins) { 'skipped' } else { $codexState }) ([bool]($codexCmd -and $codexState -ne 'unknown')) ([bool]$SkipPlugins)

$wName = ($rows | ForEach-Object { $_.Name.Length } | Measure-Object -Maximum).Maximum
$wExp = ($rows | ForEach-Object { $_.Expected.Length } | Measure-Object -Maximum).Maximum
$wAct = ($rows | ForEach-Object { $_.Actual.Length } | Measure-Object -Maximum).Maximum
Write-Color ("    {0}  {1}  {2}  {3}" -f 'name'.PadRight($wName), 'expected'.PadRight($wExp), 'actual'.PadRight($wAct), 'ok') 244
foreach ($row in $rows) {
  $color = switch ($row.Status) { 'ok' { 223 } 'skipped' { 228 } default { 203 } }
  Write-Color ("    {0}  {1}  {2}  {3}" -f $row.Name.PadRight($wName), $row.Expected.PadRight($wExp), $row.Actual.PadRight($wAct), $row.Status) $color
  if ($row.Status -eq 'FAIL') { $failures += "$($row.Name): expected $($row.Expected), got $($row.Actual)" }
}

if (-not $Check -and -not $SkipPlugins -and $codexCmd) {
  Write-Step 'codex doctor'
  $doc = Invoke-Native 'codex' @('doctor')
  $plain = [regex]::Replace($doc.Out, "$([char]27)\[[0-9;]*m", '')
  $lines = @($plain -split "`r?`n")
  $start = [array]::IndexOf(@($lines | ForEach-Object { $_.Trim() }), 'Notes')
  if ($start -ge 0) {
    # The summary is the Notes block: lines up to the first rule.
    for ($i = $start + 1; $i -lt $lines.Count -and $lines[$i].Trim().Length -gt 0 -and $lines[$i].Trim()[0] -ne [char]0x2500; $i++) {
      Write-Color "    $($lines[$i].Trim())" 244
    }
  } else {
    Write-Color "    codex doctor exited $($doc.Code)" 244
  }
  if ($plain -match 'node_repl') { Write-Color '    node_repl is a desktop-app tool; the CLI and codex exec do not have it' 228 }
}

if ($Json) {
  $docRows = @($rows | ForEach-Object { [pscustomobject]@{ name = $_.Name; expected = $_.Expected; actual = $_.Actual; status = $_.Status } })
  $out = [pscustomobject]@{ rows = $docRows; failures = @($failures) } | ConvertTo-Json -Depth 5 -Compress
  [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
  [Console]::Out.WriteLine($out)
  if ($failures.Count -gt 0) { exit 1 }
  exit 0
}
Write-Host ''
if ($failures.Count -eq 0) {
  Write-Color 'DONE: all checks passed. Restart Codex to load the new config.' 223
} else {
  Write-Color 'DONE WITH FAILURES:' 203
  $failures | ForEach-Object { Write-Color "  - $_" 203 }
  exit 1
}
