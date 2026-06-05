#!/usr/bin/env python3
"""텔레그램 웹훅을 Vercel 배포 URL로 등록/확인/삭제하는 도구.

Vercel 배포가 끝난 뒤 한 번만 실행하면 됩니다.

사용법:
  # 등록 (배포 URL의 /api/webhook 을 텔레그램에 알려줌)
  python scripts/set_webhook.py set https://your-project.vercel.app

  # 현재 등록 상태 확인
  python scripts/set_webhook.py info

  # 웹훅 해제 (폴링 방식으로 되돌릴 때)
  python scripts/set_webhook.py delete

토큰은 환경변수 TELEGRAM_BOT_TOKEN 또는 .env 에서 읽습니다.
WEBHOOK_SECRET 을 설정해두면 함께 등록해 보안을 강화합니다.
"""

import os
import sys

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다 (.env 또는 환경변수).")
    return token


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    token = _token()
    action = sys.argv[1]
    base = f"https://api.telegram.org/bot{token}"

    if action == "set":
        if len(sys.argv) < 3:
            sys.exit("사용법: set_webhook.py set https://your-project.vercel.app")
        url = sys.argv[2].rstrip("/") + "/api/webhook"
        payload = {"url": url, "drop_pending_updates": True}
        secret = os.getenv("WEBHOOK_SECRET")
        if secret:
            payload["secret_token"] = secret
        resp = requests.post(f"{base}/setWebhook", json=payload, timeout=15).json()
        print(resp)
    elif action == "info":
        print(requests.get(f"{base}/getWebhookInfo", timeout=15).json())
    elif action == "delete":
        print(requests.post(f"{base}/deleteWebhook", timeout=15).json())
    else:
        sys.exit(f"알 수 없는 명령: {action}")


if __name__ == "__main__":
    main()
