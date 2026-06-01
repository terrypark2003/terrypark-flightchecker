# Oracle Cloud "Always Free" 로 봇 24시간 무료 운영

Oracle Cloud의 Always Free VM은 **평생 무료**라, PC를 꺼도 봇이 계속 돌아갑니다.
(가입 시 카드 본인인증이 필요하지만, Always Free 자원만 쓰면 실제 청구는 없습니다.)

## 1. 가입 & VM 만들기

1. https://www.oracle.com/cloud/free/ → **Start for free** 가입
   - 카드 인증 필요(무료 등급은 청구 없음), 지역(Home Region)은 가까운 곳 선택
2. 콘솔에서 **Compute → Instances → Create Instance**
3. 설정:
   - Image: **Canonical Ubuntu** (22.04 또는 24.04)
   - Shape: **Always Free eligible** 표시가 있는 것 (예: VM.Standard.E2.1.Micro 또는 Ampere A1)
   - **SSH 키**: "Generate a key pair for me" 선택 후 **개인 키(.key) 다운로드** (꼭 보관)
4. **Create** → 잠시 뒤 인스턴스의 **Public IP** 를 메모

## 2. 서버 접속 (SSH)

윈도우 명령 프롬프트에서 (다운로드한 키 경로와 IP를 본인 값으로):

```bat
ssh -i C:\경로\ssh-key.key ubuntu@<공인IP>
```

> 처음 접속 시 yes 입력. 키 권한 오류가 나면 키 파일을 안전한 폴더로 옮겨 다시 시도.

## 3. 봇 설치 (서버 안에서)

```bash
sudo apt-get update -y && sudo apt-get install -y git
git clone https://github.com/terrypark2003/terrypark-flightchecker.git
cd terrypark-flightchecker
git checkout claude/epic-gauss-Eodjx
cp .env.example .env
nano .env     # SERPAPI_KEY, TELEGRAM_BOT_TOKEN 입력 → Ctrl+O, Enter, Ctrl+X
bash deploy/setup_server.sh
```

스크립트가 끝나면 봇이 백그라운드(systemd)에서 자동 실행되고,
서버 재부팅이나 봇 크래시 시에도 **자동으로 다시 켜집니다.**

## 4. 운영 명령

```bash
sudo systemctl status flightbot      # 상태 확인
journalctl -u flightbot -f           # 실시간 로그 (Ctrl+C로 빠져나옴)
sudo systemctl restart flightbot     # 재시작
sudo systemctl stop flightbot        # 중지
```

## 5. 코드 업데이트 시

```bash
cd terrypark-flightchecker
git pull
sudo systemctl restart flightbot
```

---

### 주의
- 같은 봇 토큰을 **PC와 서버에서 동시에** 실행하면 충돌합니다. 서버에 올렸으면 PC의 `python bot.py` 는 끄세요.
- `.env` 는 서버에만 두고 git에 커밋하지 마세요 (이미 `.gitignore` 처리됨).
