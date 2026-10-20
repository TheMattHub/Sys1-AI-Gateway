<#
.SYNOPSIS
  Start laya-serve on loopback for the System-1 gateway (Windows). No-op if something already listens on the port.
.DESCRIPTION
  /system1:choose-model copies this file to ~\.system1-gateway\engines\laya\start.ps1, next to the Laya venv,
  so it keeps working when the plugin updates. Output goes to laya-serve.log in the same folder.
  LAYA_DEVICE is left unset: laya-serve picks CUDA when available, otherwise the CPU.
#>
param(
    [string]$Model = 'typed-decisions',
    [int]$Port = 8765
)
$Root = $PSScriptRoot
$Exe = Join-Path $Root 'venv\Scripts\laya-serve.exe'
if (-not (Test-Path $Exe)) { Write-Error "laya-serve not found at $Exe; run /system1:choose-model"; exit 1 }

$probe = New-Object Net.Sockets.TcpClient
try { $probe.Connect('127.0.0.1', $Port); Write-Host "Port $Port is already in use (Laya running?)"; exit 0 }
catch { } finally { $probe.Dispose() }

$env:LAYA_MODELS = $Model
$env:LAYA_HOST = '127.0.0.1'  # laya-serve binds to 0.0.0.0 by default
$env:LAYA_PORT = "$Port"
& $Exe *>> (Join-Path $Root 'laya-serve.log')
