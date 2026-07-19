"""Vercel 서버리스 함수 — 텔레그램 웹훅 엔드포인트.

텔레그램이 메시지를 받을 때마다 이 함수를 POST로 호출합니다.
URL: https://<your-project>.vercel.app/api/webhook

환경변수(Vercel Project Settings → Environment Variables):
  - TELEGRAM_BOT_TOKEN : BotFather 봇 토큰
  - SERPAPI_KEY        : SerpApi 키
  - WEBHOOK_SECRET     : (선택) 텔레그램 시크릿 토큰 검증용
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

# 프로젝트 루트를 import 경로에 추가 (api/ 하위에서 flightchecker 패키지 접근)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightchecker.botlogic import handle_update  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _respond(self, code: int = 200, body: str = "ok") -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        # 헬스 체크용
        self._respond(200, "flightchecker webhook alive")

    def do_POST(self):
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            self._respond(500, "TELEGRAM_BOT_TOKEN not set")
            return

        # (선택) 텔레그램 시크릿 토큰 검증
        secret = os.getenv("WEBHOOK_SECRET")
        if secret:
            got = self.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if got != secret:
                self._respond(401, "unauthorized")
                return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            update = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._respond(400, "bad json")
            return

        try:
            handle_update(update, token)
        except Exception as exc:  # 어떤 경우에도 200을 돌려줘 텔레그램 재시도 폭주 방지
            print(f"handle_update error: {exc}", file=sys.stderr)

        self._respond(200, "ok")
