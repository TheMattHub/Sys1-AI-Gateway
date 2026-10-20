<#
.SYNOPSIS
  Rerun the naga System-1 bench: export the engine data, run every engine, rebuild RESULTS.md's tables.
  -Only <engine> runs one engine (then the report). Servers this script starts are stopped at the end.
  Runs in Windows PowerShell 5.1 (pwsh too): powershell -ExecutionPolicy Bypass -File bench/naga/run.ps1
#>
param([string]$Only = '', [int]$Round = 1, [string]$Arena = (Join-Path $PSScriptRoot '..\..\..\ArenaPy'))
$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$Py312 = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$Engines = "$HOME\.system1-gateway\engines"
$Bench = "$Engines\bench\Scripts\python.exe"
$env:PYTHONIOENCODING = 'utf-8'
if ($Round -eq 2) { $env:BENCH_ROUND = '2' }

function Wait-Port([int]$Port, [int]$Seconds = 300) {
    $end = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $end) {
        $c = New-Object Net.Sockets.TcpClient
        try { $c.Connect('127.0.0.1', $Port); return } catch { Start-Sleep -Seconds 2 } finally { $c.Dispose() }
    }
    throw "nothing listens on port $Port after $Seconds s"
}
function Stop-Port([int]$Port) {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
function Want($name) { -not $Only -or $Only -eq $name }

Push-Location $Here
try {
    $env:PYTHONPATH = (Resolve-Path $Arena).Path
    & $Py312 export_data.py $env:PYTHONPATH
    if (Want 'baseline') { & $Py312 eng_baseline.py }
    $env:PYTHONPATH = ''
    foreach ($e in 'harrier-bi', 'gte-rerank', 'qwen3-rerank', 'nli', 'gliner2') {
        if (Want $e) { & $Bench eng_hf.py $e }
    }
    if (Want 'laya') {
        Start-Process powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "$Engines\laya\start.ps1" -WindowStyle Hidden
        Wait-Port 8765; try { & $Bench eng_gateway.py laya } finally { Stop-Port 8765 }
    }
    if (Want 'von') {
        Start-Process "$Engines\von\venv\Scripts\von.exe" -ArgumentList 'serve', '--host', '127.0.0.1', '--port', '8777' `
            -WindowStyle Hidden -RedirectStandardOutput "$Engines\von\von-serve.log" -RedirectStandardError "$Engines\von\von-serve.err.log"
        Wait-Port 8777; try { & $Bench eng_gateway.py von } finally { Stop-Port 8777 }
    }
    if (Want 'gemma4') {
        $started = $null
        $probe = New-Object Net.Sockets.TcpClient
        try { $probe.Connect('127.0.0.1', 11434) } catch { $started = Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden -PassThru; Wait-Port 11434 } finally { $probe.Dispose() }
        try { & $Bench eng_gateway.py gemma4 } finally {
            ollama stop 'hf.co/unsloth/gemma-4-E4B-it-GGUF:Q4_K_M'
            if ($started) { Stop-Process -Id $started.Id -Force -ErrorAction SilentlyContinue }
        }
    }
    if (Want 'tuned') { & $Bench tune.py }
    if ($Only -eq 'retry-tuned') { & $Bench retry.py tuned }
    if ($Only -eq 'phase4-tuned') { & $Bench phase4.py tuned }
    if ($Only -eq 'phase4-gte') { & $Bench phase4.py gte }
    if ($Only -eq 'phase4-laya') {
        Start-Process powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "$Engines\laya\start.ps1" -WindowStyle Hidden
        Wait-Port 8765; try { & $Bench phase4.py laya } finally { Stop-Port 8765 }
    }
    if ($Only -eq 'retry-laya') {
        Start-Process powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "$Engines\laya\start.ps1" -WindowStyle Hidden
        Wait-Port 8765; try { & $Bench retry.py laya } finally { Stop-Port 8765 }
    }
    if ($Round -ne 2) { & $Bench report.py }
} finally { Pop-Location }
