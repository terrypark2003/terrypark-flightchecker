#!/usr/bin/env bash
#
# Oracle Cloud(또는 임의의 Ubuntu 서버)에서 텔레그램 봇을 24시간 띄우는 설치 스크립트.
#
# 사용법 (서버에 SSH로 접속한 뒤):
#   git clone https://github.com/terrypark2003/terrypark-flightchecker.git
#   cd terrypark-flightchecker
#   git checkout claude/epic-gauss-Eodjx
#   nano .env          # SERPAPI_KEY, TELEGRAM_BOT_TOKEN 입력 후 저장
#   bash deploy/setup_server.sh
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="$(whoami)"
SERVICE_NAME="flightbot"

echo "==> 앱 경로: $APP_DIR"
echo "==> 실행 사용자: $RUN_USER"

# 1) .env 확인
if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "!! .env 파일이 없습니다. 먼저 만들어 주세요:"
  echo "   cp .env.example .env && nano .env"
  exit 1
fi

# 2) 시스템 패키지 (python3, venv, pip)
echo "==> 시스템 패키지 설치 (sudo 비밀번호를 물어볼 수 있습니다)"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip

# 3) 가상환경 + 의존성
echo "==> 가상환경 생성 및 라이브러리 설치"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 4) systemd 서비스 등록 (자동 시작 + 꺼지면 자동 재시작)
echo "==> systemd 서비스 등록"
TMP_UNIT="$(mktemp)"
sed -e "s#__APP_DIR__#${APP_DIR}#g" \
    -e "s#__RUN_USER__#${RUN_USER}#g" \
    "$APP_DIR/deploy/flightbot.service" > "$TMP_UNIT"
sudo cp "$TMP_UNIT" "/etc/systemd/system/${SERVICE_NAME}.service"
rm -f "$TMP_UNIT"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo ""
echo "==> 완료! 봇이 백그라운드에서 돌고 있습니다."
echo "    상태 보기:  sudo systemctl status ${SERVICE_NAME}"
echo "    로그 보기:  journalctl -u ${SERVICE_NAME} -f"
echo "    재시작:     sudo systemctl restart ${SERVICE_NAME}"
echo "    중지:       sudo systemctl stop ${SERVICE_NAME}"
