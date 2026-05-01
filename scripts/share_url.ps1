# share_url.ps1
# Starts Streamlit + Cloudflare Tunnel, captures the public URL,
# copies it to clipboard, and shows a popup for easy sharing.
#
# Double-click share_url.bat to run without opening PowerShell manually.

$ProjectDir = "C:\projects\securities-analyzer"
$CloudflaredExe = "$ProjectDir\cloudflared.exe"

# Fallback to system PATH if not in project root
if (-not (Test-Path $CloudflaredExe)) {
    $CloudflaredExe = "cloudflared"
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

# ── Step 2: Start cloudflared, capture URL from log ──────────────────────────
Write-Host "[2/3] Cloudflare 터널 연결 중... (최대 40초)" -ForegroundColor Yellow

$logFile = "$env:TEMP\cloudflared_tunnel.log"
if (Test-Path $logFile) { Remove-Item $logFile -Force }

$cfProcess = Start-Process `
    -FilePath $CloudflaredExe `
    -ArgumentList "tunnel --url http://localhost:8501" `
    -RedirectStandardError $logFile `
    -NoNewWindow -PassThru

$url = $null
for ($i = 1; $i -le 40; $i++) {
    Start-Sleep -Seconds 1
    Write-Host "      대기 중... ($i/40)`r" -NoNewline -ForegroundColor DarkGray
    if (Test-Path $logFile) {
        $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        if ($content -match "https://[\w-]+\.trycloudflare\.com") {
            $url = $Matches[0]
            break
        }
    }
}

Write-Host "" # newline after the carriage-return progress line

if (-not $url) {
    Write-Host "[오류] URL을 찾지 못했습니다." -ForegroundColor Red
    Write-Host "       로그 확인: $logFile" -ForegroundColor Red
    if (-not $cfProcess.HasExited) { $cfProcess.Kill() }
    Read-Host "Enter를 눌러 종료"
    exit 1
}

# ── Step 3: Copy to clipboard ─────────────────────────────────────────────────
Set-Clipboard -Value $url

Write-Host "[3/3] URL 복사 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "  $url" -ForegroundColor Cyan
Write-Host ""

# ── Step 4: Popup ─────────────────────────────────────────────────────────────
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show(
    "URL이 클립보드에 복사됐어요!`n`n$url`n`n친구에게 카카오톡으로 붙여넣기 하세요 😊",
    "증권사 리포트 분석기",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null

# ── Keep alive: tunnel runs until this window is closed ───────────────────────
Write-Host "터널이 실행 중입니다." -ForegroundColor Green
Write-Host "이 창을 닫으면 터널이 종료됩니다." -ForegroundColor Yellow
Write-Host ""

try {
    while (-not $cfProcess.HasExited) {
        Start-Sleep -Seconds 5
    }
} finally {
    if ($cfProcess -and -not $cfProcess.HasExited) {
        $cfProcess.Kill()
    }
    Write-Host "터널이 종료되었습니다." -ForegroundColor Red
}
