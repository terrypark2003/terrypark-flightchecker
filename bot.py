#!/usr/bin/env python3
"""텔레그램 항공권 검색 봇.

코어 패키지 flightchecker 를 그대로 import해서 검색합니다.

실행 방법:
    pip install -r requirements.txt
    .env 에 SERPAPI_KEY, TELEGRAM_BOT_TOKEN 설정 후
    python bot.py

봇 사용법 (채팅창에서):
    /flight ICN FUK 2026-06-06 2026-06-07
    (출발지 도착지 출발일 [귀국일])
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from dotenv import load_dotenv

from flightchecker import FlightSearchError, SerpApiClient, search_flights
from flightchecker.formatter import format_results

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "✈️ *항공권 검색 봇*\n\n"
    "사용법:\n"
    "`/flight 출발지 도착지 출발일 [귀국일]`\n\n"
    "예시:\n"
    "• 왕복: `/flight ICN FUK 2026-06-06 2026-06-07`\n"
    "• 편도: `/flight ICN FUK 2026-06-06`\n\n"
    "공항 코드: ICN(인천) GMP(김포) FUK(후쿠오카) "
    "NRT/HND(도쿄) KIX(오사카) CJU(제주)"
)

# 키는 시작 시 한 번만 읽어 클라이언트를 공유 (요청마다 재생성 불필요).
# 키가 없으면 None으로 두고, 검색 시점에 안내 메시지를 보냅니다.
_api_key = os.getenv("SERPAPI_KEY", "")
_client = SerpApiClient(api_key=_api_key) if _api_key else None


def _is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


async def start_command(update, context):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def flight_command(update, context):
    args = context.args

    if _client is None:
        await update.message.reply_text(
            "서버에 SerpApi 키가 설정되어 있지 않습니다. "
            ".env 의 SERPAPI_KEY 를 확인하세요."
        )
        return

    if len(args) < 3:
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")
        return

    origin, destination, departure_date = args[0], args[1], args[2]
    return_date = args[3] if len(args) >= 4 else None

    # 날짜 형식 검증
    bad = [d for d in (departure_date, return_date) if d and not _is_valid_date(d)]
    if bad:
        await update.message.reply_text(
            f"날짜 형식이 올바르지 않습니다: {', '.join(bad)}\n"
            "YYYY-MM-DD 형식으로 입력하세요. 예) 2026-06-06"
        )
        return

    await update.message.reply_text("🔎 검색 중입니다...")
    try:
        offers = search_flights(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            client=_client,
        )
    except FlightSearchError as exc:
        await update.message.reply_text(f"검색 오류: {exc}")
        return

    text = format_results(
        offers,
        origin=origin.upper(),
        destination=destination.upper(),
        departure_date=departure_date,
        return_date=return_date,
    )
    await update.message.reply_text(text)


async def error_handler(update, context):
    """핸들러에서 잡지 못한 예외를 로깅하고 사용자에게 안내."""
    logger.error("처리 중 예외 발생", exc_info=context.error)
    if update and getattr(update, "message", None):
        await update.message.reply_text(
            "처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."
        )


def main() -> None:
    from telegram import BotCommand
    from telegram.ext import Application, CommandHandler

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(".env 에 TELEGRAM_BOT_TOKEN 을 설정하세요.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler("flight", flight_command))
    app.add_error_handler(error_handler)

    # 텔레그램 입력창의 명령어 메뉴(/) 등록
    async def _set_commands(application):
        await application.bot.set_my_commands(
            [
                BotCommand("flight", "항공권 검색: 출발지 도착지 출발일 [귀국일]"),
                BotCommand("help", "사용법 보기"),
            ]
        )

    app.post_init = _set_commands

    print("텔레그램 봇 실행 중... (Ctrl+C 로 종료)")
    app.run_polling()


if __name__ == "__main__":
    main()
