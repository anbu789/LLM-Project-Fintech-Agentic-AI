<#
.SYNOPSIS
    FinTech Agent Three-Terminal Windows Launcher (PowerShell 5.1 Compatible).
.DESCRIPTION
    Starts Backend API (:8001), Agent Execution Monitor, and React/Vite Frontend (:5173)
    in independent Windows PowerShell terminals with port collision safety, health verification,
    and optional non-reload integration-test mode.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start_fintech_agent.ps1
    powershell -ExecutionPolicy Bypass -File scripts\start_fintech_agent.ps1 -NoReload
    powershell -ExecutionPolicy Bypass -File scripts\start_fintech_agent.ps1 -Target backend -NoReload
    powershell -ExecutionPolicy Bypass -File scripts\start_fintech_agent.ps1 -Target monitor
    powershell -ExecutionPolicy Bypass -File scripts\start_fintech_agent.ps1 -Target frontend
#>

param(
    [ValidateSet("all", "backend", "monitor", "frontend")]
    [string]$Target = "all",

    [switch]$NoReload,

    [switch]$PlainMonitor,

    [int]$BackendPort = 8001,

    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$PythonExe = Join-Path $ProjectRoot ".venv_clean\Scripts\python.exe"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$LogsDir = Join-Path $ProjectRoot "logs"
$PidFile = Join-Path $LogsDir "launched_pids.json"

function Get-ListeningPortOwner {
    param([int]$Port)
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conns) {
            $first = $conns | Select-Object -First 1
            $proc = Get-Process -Id $first.OwningProcess -ErrorAction SilentlyContinue
            return [PSCustomObject]@{
                InUse = $true
                Pid = $first.OwningProcess
                ProcessName = if ($proc) { $proc.ProcessName } else { "unknown" }
            }
        }
    } catch {
        # Fallback below if Get-NetTCPConnection is unavailable
    }

    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $ar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $ar.AsyncWaitHandle.WaitOne(300, $false)
        if ($connected -and $client.Connected) {
            $client.EndConnect($ar)
            return [PSCustomObject]@{
                InUse = $true
                Pid = $null
                ProcessName = "unknown"
            }
        }
    } catch {
        # Port not reachable -> assume free
    } finally {
        if ($client) {
            $client.Close()
        }
    }

    return [PSCustomObject]@{
        InUse = $false
        Pid = $null
        ProcessName = $null
    }
}

function Save-PidRecord {
    param([string]$Role, [int]$ProcessId)
    if (-not (Test-Path $LogsDir)) {
        New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
    }
    $records = @{}
    if (Test-Path $PidFile) {
        try {
            $raw = Get-Content -Path $PidFile -Raw -Encoding UTF8
            if ($raw) {
                $obj = $raw | ConvertFrom-Json
                foreach ($prop in $obj.PSObject.Properties) {
                    $records[$prop.Name] = $prop.Value
                }
            }
        } catch {
            $records = @{}
        }
    }
    $records[$Role] = [PSCustomObject]@{
        pid = $ProcessId
        started_at = (Get-Date).ToString("o")
        project_root = $ProjectRoot
    }
    $records | ConvertTo-Json -Depth 4 | Set-Content -Path $PidFile -Encoding UTF8
}

function Test-Prerequisites {
    param([bool]$NeedPython, [bool]$NeedNpm)
    if ($NeedPython) {
        if (-not (Test-Path $PythonExe)) {
            Write-Host "[ERROR] Clean Python virtual environment not found at: $PythonExe" -ForegroundColor Red
            return $false
        }
    }
    if ($NeedNpm) {
        $npmCmd = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
        if (-not $npmCmd) {
            Write-Host "[ERROR] npm.cmd not found in PATH. Install Node.js before starting the frontend." -ForegroundColor Red
            return $false
        }
        if (-not (Test-Path $FrontendDir)) {
            Write-Host "[ERROR] Frontend directory not found at: $FrontendDir" -ForegroundColor Red
            return $false
        }
    }
    return $true
}

function Start-BackendTerminal {
    $owner = Get-ListeningPortOwner -Port $BackendPort
    if ($owner.InUse) {
        Write-Host "[ERROR] Port $BackendPort is already occupied (PID: $($owner.Pid), Process: $($owner.ProcessName)). Refusing to kill existing process." -ForegroundColor Red
        return $null
    }

    if ($NoReload) {
        $reloadFlags = ""
        $modeLabel = "INTEGRATION / NO-RELOAD"
    } else {
        $reloadFlags = " --reload --reload-dir `"backend\app`""
        $modeLabel = "DEV (scoped reload: backend\app only)"
    }

    $cmd = "`$Host.UI.RawUI.WindowTitle = 'FinTech Agent - Backend API (:$BackendPort)'; " +
           "Set-Location -LiteralPath '$ProjectRoot'; " +
           "Write-Host '[Terminal 1] Starting FastAPI Backend ($modeLabel) on http://127.0.0.1:$BackendPort' -ForegroundColor Cyan; " +
           "& '$PythonExe' -m uvicorn backend.app.main:app --host 127.0.0.1 --port $BackendPort$reloadFlags"

    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", $cmd) -PassThru
    Save-PidRecord -Role "backend" -ProcessId $proc.Id

    Write-Host "[*] Verifying backend health at http://127.0.0.1:$BackendPort/health ..." -ForegroundColor Yellow
    $healthy = $false
    for ($i = 0; $i -lt 30; $i++) {
        if ($proc.HasExited) {
            Write-Host "[ERROR] Backend terminal exited unexpectedly with code $($proc.ExitCode)." -ForegroundColor Red
            return $null
        }
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/health" -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200) {
                $healthy = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }

    if (-not $healthy) {
        Write-Host "[ERROR] Backend did not pass /health within 30 seconds. Check Terminal 1 window logs." -ForegroundColor Red
        return $null
    }

    Write-Host "[OK] Backend API healthy on http://127.0.0.1:$BackendPort/health (Terminal PID $($proc.Id))." -ForegroundColor Green
    return $proc
}

function Start-MonitorTerminal {
    $plainArg = if ($PlainMonitor) { " --plain" } else { "" }
    $cmd = "`$Host.UI.RawUI.WindowTitle = 'FinTech Agent - Execution Monitor'; " +
           "Set-Location -LiteralPath '$ProjectRoot'; " +
           "Write-Host '[Terminal 2] Starting FinTech Agent Execution Monitor' -ForegroundColor Cyan; " +
           "& '$PythonExe' -m backend.app.monitor$plainArg"

    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", $cmd) -PassThru
    Start-Sleep -Milliseconds 600
    if ($proc.HasExited) {
        Write-Host "[ERROR] Monitor terminal exited unexpectedly with code $($proc.ExitCode)." -ForegroundColor Red
        return $null
    }
    Save-PidRecord -Role "monitor" -ProcessId $proc.Id
    Write-Host "[OK] Execution Monitor launched (Terminal PID $($proc.Id))." -ForegroundColor Green
    return $proc
}

function Start-FrontendTerminal {
    $owner = Get-ListeningPortOwner -Port $FrontendPort
    if ($owner.InUse) {
        Write-Host "[ERROR] Port $FrontendPort is already occupied (PID: $($owner.Pid), Process: $($owner.ProcessName)). Refusing to kill existing process." -ForegroundColor Red
        return $null
    }

    $cmd = "`$Host.UI.RawUI.WindowTitle = 'FinTech Agent - Frontend (:$FrontendPort)'; " +
           "Set-Location -LiteralPath '$FrontendDir'; " +
           "Write-Host '[Terminal 3] Starting React/Vite UI on http://localhost:$FrontendPort' -ForegroundColor Cyan; " +
           "npm.cmd run dev"

    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", $cmd) -PassThru
    Save-PidRecord -Role "frontend" -ProcessId $proc.Id

    Write-Host "[*] Verifying Vite server at http://127.0.0.1:$FrontendPort ..." -ForegroundColor Yellow
    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        if ($proc.HasExited) {
            Write-Host "[ERROR] Frontend terminal exited unexpectedly with code $($proc.ExitCode)." -ForegroundColor Red
            return $null
        }
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort/" -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }

    if (-not $ready) {
        Write-Host "[WARNING] Frontend UI did not answer on http://127.0.0.1:$FrontendPort within 20 seconds. Check Terminal 3 window." -ForegroundColor Yellow
        return $null
    }

    Write-Host "[OK] Frontend UI responding on http://localhost:$FrontendPort (Terminal PID $($proc.Id))." -ForegroundColor Green
    return $proc
}

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "         FinTech Agent - Three-Terminal Launch Orchestrator (PS 5.1)" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan

$needPy = ($Target -in @("all", "backend", "monitor"))
$needNpm = ($Target -in @("all", "frontend"))

if (-not (Test-Prerequisites -NeedPython $needPy -NeedNpm $needNpm)) {
    exit 1
}

$failed = $false

if ($Target -in @("all", "backend")) {
    if (-not (Start-BackendTerminal)) { $failed = $true }
}

if ($Target -in @("all", "monitor")) {
    if (-not (Start-MonitorTerminal)) { $failed = $true }
}

if ($Target -in @("all", "frontend")) {
    if (-not (Start-FrontendTerminal)) { $failed = $true }
}

Write-Host ""
if ($failed) {
    Write-Host "[!] Startup completed with one or more errors. Check the messages above." -ForegroundColor Red
    exit 1
}

Write-Host "All requested FinTech Agent terminals started and verified:" -ForegroundColor Green
if ($Target -in @("all", "backend")) { Write-Host "  - Terminal 1 Backend API : http://127.0.0.1:$BackendPort/health" }
if ($Target -in @("all", "monitor")) { Write-Host "  - Terminal 2 Monitor     : Watching logs\execution_events.jsonl" }
if ($Target -in @("all", "frontend")) { Write-Host "  - Terminal 3 Frontend UI : http://localhost:$FrontendPort" }
Write-Host "  - Clean shutdown command : powershell -ExecutionPolicy Bypass -File scripts\stop_fintech_agent.ps1"
exit 0
