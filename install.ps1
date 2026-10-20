<#
.SYNOPSIS
  Install or upgrade the System-1 gateway for the current user (Windows PowerShell 5.1+ / PowerShell 7+).
.DESCRIPTION
  Creates a venv under ~\.system1-gateway, copies the package into it (offline, no pip), creates the
  user config if missing, and prints the `claude mcp add` command. Re-run to upgrade.
  The installed copy does not depend on this repo, so the clone can be moved or deleted afterwards.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = $(if ($env:SYSTEM1_INSTALL_DIR) { $env:SYSTEM1_INSTALL_DIR } else { Join-Path $HOME '.system1-gateway' })
)
$ErrorActionPreference = 'Stop'
$Repo = $PSScriptRoot

function Find-Python {
    # tomllib needs Python 3.11+.
    $probe = 'import sys; print(sys.executable) if sys.version_info >= (3, 11) else sys.exit(1)'
    foreach ($candidate in 'py -3.13', 'py -3.12', 'py -3.11', 'python3', 'python') {
        $exe, $rest = $candidate -split ' '
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $cmdArgs = @($rest | Where-Object { $_ }) + @('-c', $probe)
        $ErrorActionPreference = 'Continue'  # PS 5.1 turns native stderr into errors under 'Stop'
        $found = & $exe @cmdArgs 2>$null
        $ErrorActionPreference = 'Stop'
        if ($LASTEXITCODE -eq 0 -and $found) { return "$found".Trim() }
    }
    throw 'Python 3.11+ not found. Install it from https://www.python.org/downloads/ and re-run.'
}

$Python = Find-Python
$Venv = Join-Path $InstallDir 'venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'

# Reuse a working venv: while an MCP client runs the gateway, Windows locks venv\Scripts\python.exe,
# so re-running `venv` over it fails. Rebuild only if it is missing or its base Python is gone.
$healthy = $false
if (Test-Path $VenvPython) {
    $ErrorActionPreference = 'Continue'
    & $VenvPython -I -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>$null
    $healthy = $LASTEXITCODE -eq 0
    $ErrorActionPreference = 'Stop'
}
if (-not $healthy) {
    & $Python -m venv --clear --without-pip $Venv
    if ($LASTEXITCODE) { throw "venv creation failed ($Venv); close Claude Code and other MCP clients, then re-run" }
}

$Purelib = (& $VenvPython -I -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
if (-not $Purelib) { throw 'could not locate the venv site-packages' }
$Target = Join-Path $Purelib 'system1_gateway'
if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
Copy-Item -Recurse (Join-Path $Repo 'system1_gateway') $Target
Get-ChildItem $Target -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force

# -I (isolated): ignore the caller's cwd and PYTHON* env vars, so no project can shadow our imports.
$Version = (& $VenvPython -I -c 'import system1_gateway; print(system1_gateway.__version__)').Trim()
$Config = (& $VenvPython -I -c 'from system1_gateway.config import config_path; print(config_path())').Trim()
if ($LASTEXITCODE) { throw 'installed package failed to import' }

if (Test-Path $Config) {
    Write-Host "Kept existing config: $Config"
} else {
    New-Item -ItemType Directory -Force (Split-Path $Config) | Out-Null
    Copy-Item (Join-Path $Repo 'config.example.toml') $Config
    Write-Host "Created config: $Config"
}

Write-Host ""
Write-Host "Installed system1-gateway $Version into $Venv"
Write-Host ""
Write-Host "Register it with Claude Code (user scope, all projects):"
# '--' is quoted on purpose: PowerShell swallows a bare -- when `claude` is the npm claude.ps1 shim,
# and claude then rejects -I as its own option.
Write-Host "  claude mcp add --scope user --transport stdio system1 '--' `"$VenvPython`" -I -m system1_gateway"
