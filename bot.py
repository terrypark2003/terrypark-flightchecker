#!/usr/bin/env python3
"""텔레그램 봇 (미래 확장용 골격).

코어 패키지 flightchecker 를 그대로 import해서 검색합니다.
실행하려면:
    pip install python-telegram-bot
    .env 에 TELEGRAM_BOT_TOKEN 설정 후
    python bot.py

봇 명령 예시:
    /flight ICN FUK 2026-06-06 2026-06-07
    (출발지 도착지 출발일 [귀국일])
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from flightchecker import FlightSearchError, SerpApiClient, search_flights
from flightchecker.formatter import format_results

load_dotenv()

USAGE = (
    "사용법:\n"
    "/flight 출발지 도착지 출발일 [귀국일]\n\n"
    "예) /flight ICN FUK 2026-06-06 2026-06-07"
)

# 클라이언트 하나를 공유 (요청마다 새로 만들 필요 없음)
_client = SerpApiClient(api_key=os.getenv("SERPAPI_KEY", ""))


async def flight_command(update, context):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(USAGE)
        return

    origin, destination, departure_date = args[0], args[1], args[2]
    return_date = args[3] if len(args) >= 4 else None

    await update.message.reply_text("검색 중입니다... ⏳")
    try:
        offers = search_flights(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            client=_client,
        )
    except FlightSearchError as exc:
        await update.message.reply_text(f"오류: {exc}")
        return

    text = format_results(
        offers,
        origin=origin.upper(),
        destination=destination.upper(),
        departure_date=departure_date,
        return_date=return_date,
    )
    await update.message.reply_text(text)


async def start_command(update, context):
    await update.message.reply_text("항공권 검색 봇입니다.\n\n" + USAGE)


def main() -> None:
    from telegram.ext import Application, CommandHandler

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(".env 에 TELEGRAM_BOT_TOKEN 을 설정하세요.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("flight", flight_command))
    print("텔레그램 봇 실행 중... (Ctrl+C 로 종료)")
    app.run_polling()


if __name__ == "__main__":
    main()
