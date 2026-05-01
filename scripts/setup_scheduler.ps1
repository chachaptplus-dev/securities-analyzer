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
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable

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

# Task 1: Daily pipeline — scrape → reparse → sector backfill (sequential, 08:00)
# Replaces the old separate Reparse and SectorBackfill tasks.
# To remove old tasks: Unregister-ScheduledTask -TaskName "SecuritiesAnalyzer-Reparse","SecuritiesAnalyzer-SectorBackfill" -Confirm:$false
Register-AnalyzerTask `
    -TaskName   "SecuritiesAnalyzer-Daily" `
    -TaskArg    "all_ordered" `
    -Trigger    (New-ScheduledTaskTrigger -Daily -At "08:00") `
    -Description "Daily pipeline: scrape new PDFs -> LLM reparse -> sector backfill"

# Task 3: Weekly report pre-generation — every Monday at 08:00
Register-AnalyzerTask `
    -TaskName   "SecuritiesAnalyzer-WeeklyReport" `
    -TaskArg    "weekly" `
    -Trigger    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At "15:00") `
    -Description "Saturday pre-generation of weekly market report"

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

# Task 5: Streamlit app — start on login
$settingsAlways = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$actionSt = New-ScheduledTaskAction `
    -Execute "py" `
    -Argument "-3 -m streamlit run app.py" `
    -WorkingDirectory $ProjectDir

Register-ScheduledTask `
    -TaskName   "SecuritiesAnalyzer-Streamlit" `
    -Action     $actionSt `
    -Trigger    (New-ScheduledTaskTrigger -AtLogOn) `
    -Settings   $settingsAlways `
    -Description "Start Streamlit app on login" `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Output "  [OK] SecuritiesAnalyzer-Streamlit"

# Task 6: Cloudflare Tunnel — start on login (after Streamlit)
$actionCf = New-ScheduledTaskAction `
    -Execute "cloudflared" `
    -Argument "tunnel run securities-analyzer"

Register-ScheduledTask `
    -TaskName   "SecuritiesAnalyzer-Tunnel" `
    -Action     $actionCf `
    -Trigger    (New-ScheduledTaskTrigger -AtLogOn) `
    -Settings   $settingsAlways `
    -Description "Start Cloudflare Tunnel on login" `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Output "  [OK] SecuritiesAnalyzer-Tunnel"

Write-Output ""
Write-Output "=== Registration complete ==="
Write-Output ""
Write-Output "Verify with:"
Write-Output "  Get-ScheduledTask | Where-Object {`$_.TaskName -like 'SecuritiesAnalyzer*'} | Select TaskName, State"
Write-Output ""
Write-Output "Run a task manually:"
Write-Output "  Start-ScheduledTask -TaskName 'SecuritiesAnalyzer-Daily'"
Write-Output ""
Write-Output "Remove old separate tasks (if previously registered):"
Write-Output "  Unregister-ScheduledTask -TaskName 'SecuritiesAnalyzer-Reparse','SecuritiesAnalyzer-SectorBackfill' -Confirm:`$false"
Write-Output ""
Write-Output "View logs:"
Write-Output "  Get-Content $ProjectDir\data\scheduler.log -Tail 50"
