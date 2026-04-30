# start_app.ps1
# Starts Streamlit and Cloudflare Tunnel together.
# Run from any directory — paths are resolved automatically.

$ProjectDir = "C:\projects\securities-analyzer"

Write-Host ""
Write-Host "증권사 리포트 분석기 시작 중..." -ForegroundColor Cyan
Write-Host ""

# Start Streamlit in a new background window
Start-Process powershell -ArgumentList `
    "-NoExit", "-Command", `
    "cd '$ProjectDir'; py -3 -m streamlit run app.py"

Write-Host "Streamlit 시작 중... (5초 대기)" -ForegroundColor Yellow
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "Cloudflare 터널 연결 중..." -ForegroundColor Yellow
Write-Host "아래 URL을 친구에게 공유하세요!" -ForegroundColor Green
Write-Host ""

# Start Cloudflare tunnel (blocks until Ctrl+C)
cloudflared tunnel --url http://localhost:8501
