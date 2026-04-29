# Register the daily securities update as a Windows Scheduled Task.
# Run this script ONCE, from an elevated (Administrator) PowerShell session.
#
# Usage:
#   Right-click PowerShell -> "Run as administrator"
#   cd C:\projects\securities-analyzer
#   .\scripts\register_task.ps1
#
# After registration:
#   Verify : Get-ScheduledTask -TaskName 'SecuritiesAnalyzerDailyUpdate'
#   Test   : Start-ScheduledTask -TaskName 'SecuritiesAnalyzerDailyUpdate'
#   Remove : Unregister-ScheduledTask -TaskName 'SecuritiesAnalyzerDailyUpdate' -Confirm:$false

$TaskName   = "SecuritiesAnalyzerDailyUpdate"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Script      = Join-Path $ProjectRoot "scripts\daily_update.ps1"

if (-not (Test-Path $Script)) {
    Write-Error "Script not found: $Script"
    exit 1
}

# Remove existing registration so re-running this script is idempotent
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed previous task registration."
}

$Action = New-ScheduledTaskAction `
    -Execute    "powershell.exe" `
    -Argument   "-NonInteractive -ExecutionPolicy Bypass -File `"$Script`"" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -Daily -At "08:00"

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

$Principal = New-ScheduledTaskPrincipal `
    -UserId   $env:USERNAME `
    -LogonType S4U `
    -RunLevel  Limited

Register-ScheduledTask `
    -TaskName   $TaskName `
    -Action     $Action `
    -Trigger    $Trigger `
    -Settings   $Settings `
    -Principal  $Principal `
    -Description "Download and process Naver Finance research reports daily at 08:00"

Write-Host ""
Write-Host "Registered: $TaskName"
Write-Host "Runs daily at 08:00 as: $($env:USERNAME)"
Write-Host "Script:     $Script"
Write-Host "Log:        $ProjectRoot\data\daily_update.log"
Write-Host ""
Write-Host "To run immediately for testing:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
