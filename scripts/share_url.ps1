# share_url.ps1
# Starts Streamlit + Cloudflare Tunnel, captures the public URL,
# copies it to clipboard, and shows a popup for easy sharing.
#
# Double-click share_url.bat to run.

$ProjectDir    = "C:\projects\securities-analyzer"
$CloudflaredExe = "$ProjectDir\cloudflared.exe"
if (-not (Test-Path $CloudflaredExe)) { $CloudflaredExe = "cloudflared" }

# Load Windows Forms FIRST — must be in the same process before any popup calls
Add-Type -AssemblyName System.Windows.Forms

function Show-Popup {
    param([string]$Message, [string]$Title, [string]$Icon = "Information")
    [System.Windows.Forms.MessageBox]::Show(
        $Message, $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::$Icon
    ) | Out-Null
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  증권사 리포트 분석기 공유 시작" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Start Streamlit ──────────────────────────────────────────────────
Write-Host "[1/3] Streamlit 앱 시작 중..." -ForegroundColor Yellow

Start-Process powershell -ArgumentList `
    "-NoExit", "-Command", "cd '$ProjectDir'; py -3 -m streamlit run app.py" `
    -WindowStyle Minimized

Write-Host "      5초 대기..." -ForegroundColor DarkGray
Start-Sleep -Seconds 5

# ── Step 2: Start cloudflared, capture BOTH stdout and stderr ────────────────
Write-Host "[2/3] Cloudflare 터널 연결 중... (최대 40초)" -ForegroundColor Yellow

$logOut = "$env:TEMP\cf_stdout.log"
$logErr = "$env:TEMP\cf_stderr.log"
foreach ($f in $logOut, $logErr) {
    if (Test-Path $f) { Remove-Item $f -Force }
}

# Redirect stdout AND stderr to separate files — cloudflared uses stderr for logs
$cfProcess = Start-Process `
    -FilePath      $CloudflaredExe `
    -ArgumentList  "tunnel --url http://localhost:8501" `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError  $logErr `
    -NoNewWindow -PassThru

Write-Host "      cloudflared PID: $($cfProcess.Id)" -ForegroundColor DarkGray

$url = $null
for ($i = 1; $i -le 40; $i++) {
    Start-Sleep -Seconds 1

    # Check both files for the URL
    foreach ($logFile in $logOut, $logErr) {
        if (Test-Path $logFile) {
            $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
            if ($content -match "https://[a-z0-9-]+\.trycloudflare\.com") {
                $url = $Matches[0]
                break
            }
        }
    }
    if ($url) { break }

    # Debug: print last captured line every 5 seconds
    if ($i % 5 -eq 0) {
        Write-Host "  [DEBUG $i s] 로그 마지막 줄:" -ForegroundColor DarkGray
        foreach ($logFile in $logOut, $logErr) {
            if (Test-Path $logFile) {
                $tail = Get-Content $logFile -Tail 2 -ErrorAction SilentlyContinue
                if ($tail) {
                    Write-Host "    $(Split-Path $logFile -Leaf): $($tail[-1])" -ForegroundColor DarkGray
                }
            }
        }
    } else {
        Write-Host "  대기 중... ($i/40)" -ForegroundColor DarkGray
    }
}

# ── Error path ────────────────────────────────────────────────────────────────
if (-not $url) {
    Write-Host "[오류] URL을 찾지 못했습니다." -ForegroundColor Red

    # Collect last 6 lines from each log for the error popup
    $debugLines = ""
    foreach ($logFile in $logOut, $logErr) {
        if (Test-Path $logFile) {
            $tail = Get-Content $logFile -Tail 6 -ErrorAction SilentlyContinue
            if ($tail) {
                $debugLines += "`n[$(Split-Path $logFile -Leaf)]`n" + ($tail -join "`n")
            }
        }
    }

    if (-not $cfProcess.HasExited) { $cfProcess.Kill() }

    Show-Popup (
        "URL을 찾지 못했습니다. (40초 타임아웃)`n" +
        "`ncloudflared가 설치되어 있는지 확인하세요:`n$CloudflaredExe`n" +
        "`n로그 (마지막 6줄):$debugLines"
    ) "오류 — 증권사 리포트 분석기" "Error"
    exit 1
}

# ── Step 3: Copy to clipboard ─────────────────────────────────────────────────
Set-Clipboard -Value $url

Write-Host ""
Write-Host "[3/3] URL 복사 완료!" -ForegroundColor Green
Write-Host "  $url" -ForegroundColor Cyan
Write-Host ""

# ── Step 4: Popup ─────────────────────────────────────────────────────────────
Show-Popup (
    "URL이 클립보드에 복사됐어요!`n`n$url`n`n친구에게 카카오톡으로 붙여넣기 하세요 :)"
) "증권사 리포트 분석기"

# ── Keep alive: tunnel runs until this window is closed ───────────────────────
Write-Host "터널이 실행 중입니다." -ForegroundColor Green
Write-Host "이 창을 닫으면 터널이 종료됩니다." -ForegroundColor Yellow
Write-Host ""

try {
    while (-not $cfProcess.HasExited) {
        Start-Sleep -Seconds 5
    }
} finally {
    if ($cfProcess -and -not $cfProcess.HasExited) { $cfProcess.Kill() }
    Write-Host "터널이 종료되었습니다." -ForegroundColor Red
}
