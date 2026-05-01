# share_url.ps1
# Start Streamlit first: py -3 -m streamlit run app.py
# Then run this script to get a shareable Cloudflare URL.

# Step 1: Clear clipboard
Set-Clipboard -Value ""

# Step 2: Start cloudflared in background, log to temp file
$logFile = "$env:TEMP\cloudflared_output.txt"
Remove-Item $logFile -ErrorAction SilentlyContinue
Start-Process -FilePath "cloudflared" `
    -ArgumentList "tunnel --url http://localhost:8501" `
    -RedirectStandardError $logFile `
    -WindowStyle Hidden

# Step 3: Poll log file for URL (wait up to 60 seconds)
$url = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $logFile) {
        $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        Write-Host "[$i초] 로그 확인 중..."
        if ($content) { Write-Host $content[-200..-1] }
        if ($content -match 'https://([a-z0-9\-]+\.trycloudflare\.com)') {
            $url = $matches[0]
            break
        }
    }
}

# Step 4: Result
if ($url) {
    Set-Clipboard -Value $url
    Write-Host "URL 복사됨: $url" -ForegroundColor Green
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("URL 복사됨!`n`n$url`n`n카카오톡에 붙여넣기 하세요", "완료")
} else {
    Write-Host "URL을 찾지 못했습니다. 로그:" -ForegroundColor Red
    Get-Content $logFile -ErrorAction SilentlyContinue
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("URL을 찾지 못했습니다.`n로그파일: $logFile", "실패")
}
