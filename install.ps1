$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ManagePy = Join-Path $RepoDir "scripts\manage.py"

$PyCmd = $null
foreach ($cand in @("py", "python3", "python")) {
  $cmd = Get-Command $cand -ErrorAction SilentlyContinue
  if (-not $cmd) { continue }
  try {
    if ($cand -eq "py") {
      & py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) { $PyCmd = @("py", "-3"); break }
    } else {
      & $cmd.Source -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) { $PyCmd = @($cmd.Source); break }
    }
  } catch {}
}

if (-not $PyCmd) {
  Write-Error "Python 3.9+ is required to install Antigravity Usage Monitor."
  exit 1
}

if ($PyCmd.Count -gt 1) {
  & $PyCmd[0] $PyCmd[1] $ManagePy install @args
} else {
  & $PyCmd[0] $ManagePy install @args
}
exit $LASTEXITCODE
