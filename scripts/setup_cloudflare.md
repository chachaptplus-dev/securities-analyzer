# Cloudflare Tunnel 설정 가이드

## 1. cloudflared 설치

PowerShell (관리자 권한):

```powershell
winget install Cloudflare.cloudflared
```

설치 확인:

```powershell
cloudflared --version
```

---

## 2. Cloudflare 로그인

```powershell
cloudflared tunnel login
```

브라우저가 열리면 Cloudflare 계정으로 로그인합니다. 무료 계정으로 가능합니다.

---

## 3. 터널 생성 (최초 1회)

```powershell
cloudflared tunnel create securities-analyzer
```

생성 후 터널 ID를 메모해 두세요 (예: `a1b2c3d4-...`).

---

## 4. 설정 파일 생성

`C:\Users\{사용자}\.cloudflared\config.yml` 파일을 생성합니다:

```yaml
tunnel: securities-analyzer
credentials-file: C:\Users\{사용자}\.cloudflared\{tunnel-id}.json

ingress:
  - service: http://localhost:8501
  - service: http_status:404
```

`{사용자}` 와 `{tunnel-id}` 는 실제 값으로 교체하세요.

---

## 5. 고정 도메인 연결 (선택)

**Cloudflare에 등록된 도메인이 있는 경우:**

```powershell
cloudflared tunnel route dns securities-analyzer your-domain.com
```

**도메인이 없는 경우 (임시 URL):**

```powershell
cloudflared tunnel --url http://localhost:8501
```

터미널에 출력된 `https://xxxx-xxxx.trycloudflare.com` URL을 공유하면 됩니다.
앱을 재시작할 때마다 URL이 바뀝니다.

---

## 6. 터널 실행 (config.yml 사용 시)

```powershell
cloudflared tunnel run securities-analyzer
```

---

## 간편 실행

- `scripts\start_app_simple.bat` 더블클릭 — Streamlit + Cloudflare 터널 한 번에 시작
- `scripts\start_app.ps1` — PowerShell에서 실행 (색상 출력)

---

## 주의사항

- Cloudflare Tunnel은 인터넷에 앱을 공개합니다. 민감한 데이터 업로드 시 주의하세요.
- 임시 URL(`trycloudflare.com`)은 `cloudflared` 프로세스가 살아있는 동안만 유효합니다.
- 앱 종료 시 터미널 창 두 개(Streamlit, cloudflared)를 모두 닫으세요.
