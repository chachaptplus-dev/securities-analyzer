# Register the daily securities update as a Windows Scheduled Task.
# No administrator rights required.
#
# The task uses Interactive logon: it runs while you are logged in,
# which is the standard for personal-machine daily tasks.
#
# Usage (normal PowerShell, no elevation needed):
#   cd C:\projects\securities-analyzer
#   .\scripts\register_task.ps1
#
# After registration:
#   Verify : Get-ScheduledTask -TaskName 'SecuritiesAnalyzerDailyUpdate'
#   Test   : Start-ScheduledTask -TaskName 'SecuritiesAnalyzerDailyUpdate'
#   Remove : Unregister-ScheduledTask -TaskName 'SecuritiesAnalyzerDailyUpdate' -Confirm:$false

$TaskName    = "SecuritiesAnalyzerDailyUpdate"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Script      = Join-Path $ProjectRoot "scripts\daily_update.ps1"

if (-not (Test-Path $Script)) {
    Write-Error "Script not found: $Script"
    exit 1
}

# Remove existing registration (idempotent re-runs)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction `
    -Execute          "powershell.exe" `
    -Argument         "-NonInteractive -ExecutionPolicy Bypass -File `"$Script`"" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -Daily -At "08:00"

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

# Interactive logon: no admin or batch-logon rights needed.
# S4U was removed — it requires "Log on as a batch job" privilege (admin only).
$Principal = New-ScheduledTaskPrincipal `
    -UserId    $env:USERNAME `
    -LogonType Interactive `
    -RunLevel  Limited

$registered = $false

try {
    Register-ScheduledTask `
        -TaskName    $TaskName `
        -Action      $Action `
        -Trigger     $Trigger `
        -Settings    $Settings `
        -Principal   $Principal `
        -Description "Download and process Naver Finance research reports daily at 08:00" `
        -ErrorAction Stop | Out-Null
    $registered = $true
    Write-Host "Registered via Register-ScheduledTask."
} catch {
    Write-Warning "Register-ScheduledTask failed: $_"
    Write-Host "Falling back to schtasks.exe..."

    # Fallback: write a tiny .cmd wrapper so schtasks /TR has no embedded-quote issues
    $wrapper = Join-Path $ProjectRoot "scripts\_run_daily.cmd"
    "@echo off`r`npowershell.exe -NonInteractive -ExecutionPolicy Bypass -File `"$Script`"" |
        Out-File -FilePath $wrapper -Encoding ascii
    Write-Host "Created wrapper: $wrapper"

    schtasks /Create /TN $TaskName /TR $wrapper /SC DAILY /ST 08:00 /RL LIMITED /F
    if ($LASTEXITCODE -eq 0) {
        $registered = $true
        Write-Host "Registered via schtasks.exe."
    }
}

if (-not $registered) {
    Write-Error "Registration failed. Try running PowerShell as Administrator."
    exit 1
}

Write-Host ""
Write-Host "Task      : $TaskName"
Write-Host "Runs      : daily at 08:00 as $($env:USERNAME) (while logged in)"
Write-Host "Script    : $Script"
Write-Host "Log       : $ProjectRoot\data\daily_update.log"
Write-Host ""
Write-Host "To run now    : Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To view log   : Get-Content '$ProjectRoot\data\daily_update.log' -Tail 30"
