# setup_scheduler.ps1
# Registers Windows Task Scheduler tasks for the securities analyzer.
# Run as Administrator:  .\scripts\setup_scheduler.ps1

$ProjectDir = "C:\projects\securities-analyzer"
$PythonExe  = "py"
$ScriptPath = "$ProjectDir\scripts\scheduled_tasks.py"

function Register-AnalyzerTask {
    param(
        [string]$TaskName,
        [string]$TaskArg,
        $Trigger,
        [string]$Description
    )

    $action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument "-3 `"$ScriptPath`" --task $TaskArg" `
        -WorkingDirectory $ProjectDir

    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -RestartCount 1 `
        -RestartInterval (New-TimeSpan -Minutes 10) `
        -StartWhenAvailable

    Register-ScheduledTask `
        -TaskName    $TaskName `
        -Action      $action `
        -Trigger     $Trigger `
        -Settings    $settings `
        -Description $Description `
        -RunLevel    Highest `
        -Force | Out-Null

    Write-Output "  [OK] $TaskName"
}

Write-Output ""
Write-Output "=== Registering SecuritiesAnalyzer scheduled tasks ==="
Write-Output ""

# Task 1: LLM reparse — every day at 09:00
Register-AnalyzerTask `
    -TaskName   "SecuritiesAnalyzer-Reparse" `
    -TaskArg    "reparse" `
    -Trigger    (New-ScheduledTaskTrigger -Daily -At "09:00") `
    -Description "Daily LLM re-parse of UNKNOWN/NULL rows in securities DB"

# Task 2: Sector backfill — every day at 09:05 (runs fast, after reparse)
Register-AnalyzerTask `
    -TaskName   "SecuritiesAnalyzer-SectorBackfill" `
    -TaskArg    "sector" `
    -Trigger    (New-ScheduledTaskTrigger -Daily -At "09:05") `
    -Description "Daily NULL-sector backfill"

# Task 3: Weekly report pre-generation — every Monday at 08:00
Register-AnalyzerTask `
    -TaskName   "SecuritiesAnalyzer-WeeklyReport" `
    -TaskArg    "weekly" `
    -Trigger    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "08:00") `
    -Description "Monday pre-generation of weekly market report"

# Task 4: Stock master update — 1st of every month at 07:00
try {
    $monthlyTrigger = New-ScheduledTaskTrigger -Monthly -DaysOfMonth 1 -At "07:00"
    Register-AnalyzerTask `
        -TaskName   "SecuritiesAnalyzer-StockMaster" `
        -TaskArg    "stock_master" `
        -Trigger    $monthlyTrigger `
        -Description "Monthly refresh of data/stock_master.csv via pykrx"
} catch {
    # Fallback: daily trigger — script checks internally if it's the 1st
    Write-Warning "Monthly trigger not supported — falling back to daily at 07:00"
    Register-AnalyzerTask `
        -TaskName   "SecuritiesAnalyzer-StockMaster" `
        -TaskArg    "stock_master" `
        -Trigger    (New-ScheduledTaskTrigger -Daily -At "07:00") `
        -Description "Monthly refresh of stock_master.csv (checks date internally)"
}

Write-Output ""
Write-Output "=== Registration complete ==="
Write-Output ""
Write-Output "Verify with:"
Write-Output "  Get-ScheduledTask | Where-Object {`$_.TaskName -like 'SecuritiesAnalyzer*'} | Select TaskName, State"
Write-Output ""
Write-Output "Run a task manually:"
Write-Output "  Start-ScheduledTask -TaskName 'SecuritiesAnalyzer-Reparse'"
Write-Output ""
Write-Output "View logs:"
Write-Output "  Get-Content $ProjectDir\data\scheduler.log -Tail 50"
