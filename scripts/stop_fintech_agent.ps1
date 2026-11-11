<#
.SYNOPSIS
    FinTech Agent Clean Shutdown Script (PowerShell 5.1 Compatible).
.DESCRIPTION
    Safely stops only the FinTech Agent terminal process trees recorded in logs\launched_pids.json
    and removes stale PID metadata without terminating unrelated processes.
#>

$ErrorActionPreference = "SilentlyContinue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$PidFile = Join-Path $ProjectRoot "logs\launched_pids.json"

function Stop-ProcessTreeSafe {
    param([int]$RootPid)
    if ($RootPid -le 0) { return }
    # Stop child processes spawned inside the PowerShell window first
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $RootPid" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTreeSafe -RootPid $child.ProcessId
    }
    $target = Get-Process -Id $RootPid -ErrorAction SilentlyContinue
    if ($target) {
        Stop-Process -Id $RootPid -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path $PidFile)) {
    Write-Host "[INFO] No active FinTech Agent launcher PID record found at $PidFile." -ForegroundColor Yellow
    exit 0
}

try {
    $raw = Get-Content -Path $PidFile -Raw -Encoding UTF8
    $data = $raw | ConvertFrom-Json
} catch {
    Write-Host "[WARNING] Could not parse PID record at $PidFile." -ForegroundColor Yellow
    exit 1
}

foreach ($prop in $data.PSObject.Properties) {
    $role = $prop.Name
    $entry = $prop.Value
    $targetPid = [int]$entry.pid
    $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "[*] Stopping FinTech Agent '$role' terminal tree (PID $targetPid)..." -ForegroundColor Cyan
        Stop-ProcessTreeSafe -RootPid $targetPid
        Write-Host "[OK] Stopped '$role' (PID $targetPid)." -ForegroundColor Green
    } else {
        Write-Host "[INFO] Recorded '$role' PID $targetPid is no longer running." -ForegroundColor DarkGray
    }
}

Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "[OK] Clean shutdown complete." -ForegroundColor Green
exit 0
