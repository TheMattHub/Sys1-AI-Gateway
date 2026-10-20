<#
.SYNOPSIS
  Remove the System-1 gateway for the current user. Keeps the config unless -Purge is given.
#>
[CmdletBinding()]
param(
    [switch]$Purge,
    [string]$InstallDir = $(if ($env:SYSTEM1_INSTALL_DIR) { $env:SYSTEM1_INSTALL_DIR } else { Join-Path $HOME '.system1-gateway' })
)
$ErrorActionPreference = 'Stop'

if (Get-Command claude -ErrorAction SilentlyContinue) {
    $ErrorActionPreference = 'Continue'  # "not found" is fine: maybe it was never registered
    claude mcp remove --scope user system1 2>&1 | Out-Host
    $ErrorActionPreference = 'Stop'
}

$Venv = Join-Path $InstallDir 'venv'
if (Test-Path $Venv) {
    Remove-Item -Recurse -Force $Venv
    Write-Host "Removed $Venv"
}

# Created by /system1:choose-model when the user asked for the engine to start at login.
$Startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\system1-laya.cmd'
if (Test-Path $Startup) { Remove-Item -Force $Startup; Write-Host "Removed login entry $Startup" }

# Engines (Laya's venv and checkpoint are several GB) and logs: only with -Purge. Stop the engine first,
# Windows cannot delete a running laya-serve.exe.
foreach ($dir in 'engines', 'logs') {
    $path = Join-Path $InstallDir $dir
    if (-not (Test-Path $path)) { continue }
    if ($Purge) { Remove-Item -Recurse -Force $path; Write-Host "Removed $path" }
    else { Write-Host "Kept $path (re-run with -Purge to remove it)" }
}
if ((Test-Path $InstallDir) -and -not (Get-ChildItem -Force $InstallDir)) { Remove-Item $InstallDir }

# A custom SYSTEM1_CONFIG may live in a shared folder: purge only that file, never its directory.
$ConfigPath = if ($env:SYSTEM1_CONFIG) { $env:SYSTEM1_CONFIG } else { Join-Path $env:APPDATA 'system1' }
if ($Purge) {
    if (Test-Path $ConfigPath) { Remove-Item -Recurse -Force $ConfigPath; Write-Host "Removed $ConfigPath" }
    Write-Host "Model downloads are cached by Hugging Face in ~\.cache\huggingface\hub; delete models--convaiinnovations--* there if you want the disk space back."
} else {
    Write-Host "Kept config: $ConfigPath (re-run with -Purge to remove it)"
}
