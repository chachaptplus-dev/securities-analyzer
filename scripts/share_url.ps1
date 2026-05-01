# share_url.ps1
# Starts Cloudflare Tunnel and shares the public URL via clipboard + popup.
# Start Streamlit manually first: py -3 -m streamlit run app.py

Add-Type -AssemblyName System.Windows.Forms

$LogFile = "$env:TEMP\cf.log"

# ── 1. Kill existing cloudflared processes ────────────────────────────────────
Write-Host "기존 cloudflared 프로세스 종료 중..." -ForegroundColor Yellow
Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue | Stop-Process -Force
if (Test-Path $LogFile) { Remove-Item $LogFile -Force }
Start-Sleep -Seconds 1

# ── 2. Start cloudflared in a new visible window ──────────────────────────────
Write-Host "Cloudflare 터널 시작 중..." -ForegroundColor Cyan
$cf = Start-Process "cloudflared" `
    -ArgumentList "tunnel --url http://localhost:8501" `
    -PassThru `
    -RedirectStandardError $LogFile

Write-Host "cloudflared PID: $($cf.Id)" -ForegroundColor DarkGray

# ── 3. Wait 15 seconds ────────────────────────────────────────────────────────
Write-Host "15초 대기 중..." -ForegroundColor Yellow
for ($i = 1; $i -le 15; $i++) {
    Start-Sleep -Seconds 1
    Write-Host "  $i/15..." -ForegroundColor DarkGray
}

# ── 4. Read log and find URL ──────────────────────────────────────────────────
Write-Host ""
Write-Host "로그 파일 읽는 중: $LogFile" -ForegroundColor DarkGray

$log = Get-Content $LogFile -Raw -ErrorAction SilentlyContinue
$match = [regex]::Match($log, 'https://[a-z0-9\-]+\.trycloudflare\.com')

# ── 5a. URL found ─────────────────────────────────────────────────────────────
if ($match.Success) {
    $url = $match.Value
    Write-Host ""
    Write-Host "URL 발견: $url" -ForegroundColor Green

    Set-Clipboard -Value $url

    [System.Windows.Forms.MessageBox]::Show(
        "URL이 클립보드에 복사됐어요!`n`n$url`n`n친구에게 카카오톡으로 붙여넣기 하세요 :)",
        "증권사 리포트 분석기",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null

    Write-Host ""
    Write-Host "터널 실행 중 — 이 창을 닫으면 종료됩니다." -ForegroundColor Yellow
    try {
        Wait-Process -Id $cf.Id -ErrorAction SilentlyContinue
    } finally {
        if (-not $cf.HasExited) { $cf.Kill() }
    }

# ── 5b. URL not found — print full log ───────────────────────────────────────
} else {
    Write-Host ""
    Write-Host "========== URL을 찾지 못했습니다 ==========" -ForegroundColor Red
    Write-Host "로그 전체 내용:" -ForegroundColor Red
    Write-Host "-------------------------------------------" -ForegroundColor DarkGray
    Write-Host $log
    Write-Host "-------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "cloudflared가 설치되어 있는지 확인:" -ForegroundColor Yellow
    Write-Host "  where cloudflared" -ForegroundColor Yellow
    Write-Host "  cloudflared --version" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Enter를 눌러 종료"
    if (-not $cf.HasExited) { $cf.Kill() }
}
