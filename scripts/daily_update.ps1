# Daily securities report update
# 1. Scrape new PDFs from Naver Finance
# 2. Process new PDFs into the database
#
# Designed to be run by Windows Task Scheduler.
# Log written to data\daily_update.log

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$LogFile = Join-Path $ProjectRoot "data\daily_update.log"

function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Output $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Log "=== Daily update started ==="

# --- Step 1: Scrape ---
Write-Log "Step 1: scraping new PDFs..."
$scrapeOut = & py -3 "$ProjectRoot\src\scraper.py" 2>&1
$scrapeExit = $LASTEXITCODE
$scrapeOut | ForEach-Object { Write-Log "  [scraper] $_" }

if ($scrapeExit -ne 0) {
    Write-Log "WARNING: scraper exited with code $scrapeExit — continuing to ingest anyway"
}

# --- Step 2: Ingest into database ---
Write-Log "Step 2: ingesting new PDFs into database..."
$ingestOut = & py -3 "$ProjectRoot\src\ingest.py" 2>&1
$ingestExit = $LASTEXITCODE
$ingestOut | ForEach-Object { Write-Log "  [ingest] $_" }

if ($ingestExit -ne 0) {
    Write-Log "ERROR: ingest failed with exit code $ingestExit"
    Write-Log "=== Daily update FAILED ==="
    exit 1
}

Write-Log "=== Daily update complete ==="
