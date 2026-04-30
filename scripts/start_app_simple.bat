@echo off
echo.
echo 증권사 리포트 분석기 시작...
echo.

cd /d C:\projects\securities-analyzer

echo [1/2] Streamlit 앱 시작 중...
start "Streamlit" py -3 -m streamlit run app.py

echo [2/2] 5초 후 Cloudflare 터널 연결...
timeout /t 5 /nobreak > nul

echo.
echo Cloudflare 터널 연결 중...
echo 출력된 URL을 공유하세요!
echo.
cloudflared tunnel --url http://localhost:8501

pause
