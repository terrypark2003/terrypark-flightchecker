#!/usr/bin/env python3
"""텔레그램 항공권 검색 봇.

기능:
- /flight  : 항공권 검색 (한글 공항명 입력 가능, 예: 인천 후쿠오카)
- /flex    : 출발일 ±며칠 날짜별 최저가 비교
- /watch   : 목표가 이하로 떨어지면 자동 알림 등록
- /watches : 등록한 알림 목록
- /unwatch : 알림 삭제
- 버튼(/menu): 출발지·도착지·날짜를 버튼으로 선택

코어 패키지 flightchecker 를 그대로 import해서 검색합니다.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from flightchecker import (
    FlightSearchError,
    SerpApiClient,
    Watch,
    WatchStore,
    cheapest_price,
    resolve_airport,
    search_flexible_dates,
    search_flights,
)
from flightchecker.formatter import format_flexible, format_results

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "✈️ *항공권 검색 봇*\n\n"
    "*검색*\n"
    "`/flight 출발 도착 출발일 [귀국일]`\n"
    "예) `/flight 인천 후쿠오카 2026-06-06 2026-06-07`\n"
    "(공항 이름은 한글로 입력해도 됩니다)\n\n"
    "*날짜별 최저가* (±3일 비교)\n"
    "`/flex 출발 도착 기준출발일 [귀국일]`\n"
    "예) `/flex 인천 후쿠오카 2026-06-06 2026-06-07`\n\n"
    "*가격 알림*\n"
    "`/watch 출발 도착 출발일 [귀국일] 목표가`\n"
    "예) `/watch 인천 후쿠오카 2026-06-06 2026-06-07 200000`\n"
    "목표가 이하로 떨어지면 자동으로 알려줍니다.\n"
    "`/watches` 목록 · `/unwatch 번호` 삭제\n\n"
    "*버튼으로 검색*: /menu"
)

# 가격 알림 검사 주기(초). 기본 6시간.
WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL_SEC", str(6 * 3600)))

_api_key = os.getenv("SERPAPI_KEY", "")
_client = SerpApiClient(api_key=_api_key) if _api_key else None
_store = WatchStore()


# ---- 입력 파싱 헬퍼 ----------------------------------------------------

def _is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _resolve_pair(origin: str, destination: str) -> tuple[str, str]:
    """출발/도착을 IATA 코드로 변환 (실패 시 ValueError)."""
    return resolve_airport(origin), resolve_airport(destination)


# ---- 명령어 핸들러 ----------------------------------------------------

async def start_command(update, context):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def flight_command(update, context):
    if _client is None:
        await update.message.reply_text("서버에 SERPAPI_KEY 가 설정되지 않았습니다.")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")
        return

    try:
        origin, destination = _resolve_pair(args[0], args[1])
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    departure_date = args[2]
    return_date = args[3] if len(args) >= 4 else None
    bad = [d for d in (departure_date, return_date) if d and not _is_valid_date(d)]
    if bad:
        await update.message.reply_text(
            f"날짜 형식 오류: {', '.join(bad)} (YYYY-MM-DD 로 입력)"
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

    await update.message.reply_text(
        format_results(offers, origin, destination, departure_date, return_date)
    )


async def flex_command(update, context):
    if _client is None:
        await update.message.reply_text("서버에 SERPAPI_KEY 가 설정되지 않았습니다.")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "사용법: /flex 출발 도착 기준출발일 [귀국일]\n"
            "예) /flex 인천 후쿠오카 2026-06-06 2026-06-07"
        )
        return

    try:
        origin, destination = _resolve_pair(args[0], args[1])
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    base_date = args[2]
    return_date = args[3] if len(args) >= 4 else None
    bad = [d for d in (base_date, return_date) if d and not _is_valid_date(d)]
    if bad:
        await update.message.reply_text(f"날짜 형식 오류: {', '.join(bad)}")
        return

    await update.message.reply_text("📅 날짜별 최저가를 조사 중입니다... (조금 걸립니다)")
    try:
        results = search_flexible_dates(
            origin=origin,
            destination=destination,
            base_date=base_date,
            flex_days=3,
            return_date=return_date,
            client=_client,
        )
    except FlightSearchError as exc:
        await update.message.reply_text(f"검색 오류: {exc}")
        return

    await update.message.reply_text(format_flexible(results, origin, destination))


async def watch_command(update, context):
    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "사용법: /watch 출발 도착 출발일 [귀국일] 목표가\n"
            "예) /watch 인천 후쿠오카 2026-06-06 2026-06-07 200000"
        )
        return

    # 마지막 인자는 목표가(숫자)
    try:
        target_price = float(args[-1].replace(",", ""))
    except ValueError:
        await update.message.reply_text("목표가는 숫자로 입력하세요. 예) 200000")
        return

    middle = args[2:-1]  # 출발일 [귀국일]
    if not middle or len(middle) > 2:
        await update.message.reply_text("날짜를 출발일 [귀국일] 형식으로 입력하세요.")
        return

    try:
        origin, destination = _resolve_pair(args[0], args[1])
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    departure_date = middle[0]
    return_date = middle[1] if len(middle) == 2 else None
    bad = [d for d in (departure_date, return_date) if d and not _is_valid_date(d)]
    if bad:
        await update.message.reply_text(f"날짜 형식 오류: {', '.join(bad)}")
        return

    watch = Watch(
        chat_id=update.effective_chat.id,
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        target_price=target_price,
    )
    if _store.add(watch):
        trip = f"{departure_date}~{return_date}" if return_date else departure_date
        await update.message.reply_text(
            f"🔔 알림 등록 완료\n{origin}→{destination} {trip}\n"
            f"목표가 {target_price:,.0f} KRW 이하가 되면 알려드릴게요.\n"
            f"(약 {WATCH_INTERVAL // 3600}시간마다 자동 확인)"
        )
    else:
        await update.message.reply_text("이미 같은 조건의 알림이 등록되어 있습니다.")


async def watches_command(update, context):
    items = _store.list_for(update.effective_chat.id)
    if not items:
        await update.message.reply_text("등록된 가격 알림이 없습니다. /watch 로 등록하세요.")
        return
    lines = ["🔔 등록된 가격 알림:"]
    for i, w in enumerate(items, start=1):
        trip = f"{w.departure_date}~{w.return_date}" if w.return_date else w.departure_date
        last = f" (최근 {w.last_price:,.0f})" if w.last_price else ""
        lines.append(
            f"{i}. {w.origin}→{w.destination} {trip} · 목표 {w.target_price:,.0f} KRW{last}"
        )
    lines.append("\n삭제: /unwatch 번호")
    await update.message.reply_text("\n".join(lines))


async def unwatch_command(update, context):
    args = context.args
    if len(args) != 1 or not args[0].isdigit():
        await update.message.reply_text("사용법: /unwatch 번호  (번호는 /watches 로 확인)")
        return
    removed = _store.remove(update.effective_chat.id, int(args[0]))
    if removed:
        await update.message.reply_text(
            f"삭제됨: {removed.origin}→{removed.destination} {removed.departure_date}"
        )
    else:
        await update.message.reply_text("해당 번호의 알림을 찾을 수 없습니다.")


# ---- 가격 알림 주기 검사 (JobQueue) -----------------------------------

async def check_watches(context):
    """등록된 모든 watch를 검사해 목표가 도달 시 알림."""
    if _client is None:
        return
    for w in _store.all():
        try:
            offers = search_flights(
                origin=w.origin,
                destination=w.destination,
                departure_date=w.departure_date,
                return_date=w.return_date,
                non_stop=w.non_stop,
                client=_client,
            )
        except Exception as exc:
            logger.warning("watch 검사 실패 %s: %s", w.key, exc)
            continue

        price = cheapest_price(offers)
        w.last_price = price
        if price is not None and price <= w.target_price and not w.notified:
            w.notified = True
            trip = f"{w.departure_date}~{w.return_date}" if w.return_date else w.departure_date
            await context.bot.send_message(
                chat_id=w.chat_id,
                text=(
                    f"🎉 가격 알림!\n{w.origin}→{w.destination} {trip}\n"
                    f"현재 최저가 {price:,.0f} KRW (목표 {w.target_price:,.0f} 이하)\n\n"
                    f"자세히: /flight {w.origin} {w.destination} {w.departure_date}"
                    + (f" {w.return_date}" if w.return_date else "")
                ),
            )
        elif price is not None and price > w.target_price:
            # 다시 올라가면 알림 재무장
            w.notified = False
    _store.save()  # 갱신된 last_price / notified 상태를 디스크에 반영


# ---- 버튼 UI ----------------------------------------------------------

_POPULAR = [
    ("인천", "ICN"), ("김포", "GMP"), ("부산", "PUS"), ("제주", "CJU"),
    ("후쿠오카", "FUK"), ("도쿄", "NRT"), ("오사카", "KIX"), ("삿포로", "CTS"),
    ("방콕", "BKK"), ("다낭", "DAD"), ("타이베이", "TPE"), ("홍콩", "HKG"),
]


def _airport_keyboard(stage: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows, row = [], []
    for name, code in _POPULAR:
        row.append(InlineKeyboardButton(name, callback_data=f"{stage}:{code}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _date_keyboard(stage: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    today = datetime.now().date()
    rows, row = [], []
    for offset in range(1, 15):  # 내일부터 2주
        d = today + timedelta(days=offset)
        row.append(
            InlineKeyboardButton(d.strftime("%m/%d"), callback_data=f"{stage}:{d.isoformat()}")
        )
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def menu_command(update, context):
    context.user_data["wizard"] = {}
    await update.message.reply_text(
        "출발지를 선택하세요 ✈️", reply_markup=_airport_keyboard("origin")
    )


async def on_button(update, context):
    query = update.callback_query
    await query.answer()
    stage, _, value = query.data.partition(":")
    wiz = context.user_data.setdefault("wizard", {})

    if stage == "origin":
        wiz["origin"] = value
        await query.edit_message_text(
            f"출발: {value}\n도착지를 선택하세요", reply_markup=_airport_keyboard("dest")
        )
    elif stage == "dest":
        wiz["dest"] = value
        await query.edit_message_text(
            f"{wiz['origin']} → {value}\n출발일을 선택하세요",
            reply_markup=_date_keyboard("out"),
        )
    elif stage == "out":
        wiz["out"] = value
        await query.edit_message_text(
            f"{wiz['origin']} → {wiz['dest']}\n출발일 {value}\n귀국일을 선택하세요 (편도면 '편도' 선택)",
            reply_markup=_return_keyboard(),
        )
    elif stage == "ret":
        wiz["ret"] = None if value == "oneway" else value
        await _run_wizard_search(query, context, wiz)


def _return_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    today = datetime.now().date()
    rows = [[InlineKeyboardButton("편도 (귀국 없음)", callback_data="ret:oneway")]]
    row = []
    for offset in range(1, 15):
        d = today + timedelta(days=offset)
        row.append(InlineKeyboardButton(d.strftime("%m/%d"), callback_data=f"ret:{d.isoformat()}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def _run_wizard_search(query, context, wiz):
    if _client is None:
        await query.edit_message_text("서버에 SERPAPI_KEY 가 설정되지 않았습니다.")
        return
    origin, dest, out, ret = wiz["origin"], wiz["dest"], wiz["out"], wiz.get("ret")
    await query.edit_message_text("🔎 검색 중입니다...")
    try:
        offers = search_flights(
            origin=origin, destination=dest, departure_date=out,
            return_date=ret, client=_client,
        )
    except FlightSearchError as exc:
        await query.edit_message_text(f"검색 오류: {exc}")
        return
    await query.edit_message_text(format_results(offers, origin, dest, out, ret))


async def error_handler(update, context):
    logger.error("처리 중 예외 발생", exc_info=context.error)
    if update and getattr(update, "message", None):
        await update.message.reply_text("처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.")


def main() -> None:
    from telegram import BotCommand
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
    )

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(".env 에 TELEGRAM_BOT_TOKEN 을 설정하세요.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler("flight", flight_command))
    app.add_handler(CommandHandler("flex", flex_command))
    app.add_handler(CommandHandler("watch", watch_command))
    app.add_handler(CommandHandler("watches", watches_command))
    app.add_handler(CommandHandler("unwatch", unwatch_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_error_handler(error_handler)

    # 가격 알림 주기 검사
    if app.job_queue:
        app.job_queue.run_repeating(check_watches, interval=WATCH_INTERVAL, first=30)

    async def _set_commands(application):
        await application.bot.set_my_commands(
            [
                BotCommand("flight", "항공권 검색"),
                BotCommand("flex", "날짜별 최저가 (±3일)"),
                BotCommand("watch", "가격 알림 등록"),
                BotCommand("watches", "내 알림 목록"),
                BotCommand("unwatch", "알림 삭제"),
                BotCommand("menu", "버튼으로 검색"),
                BotCommand("help", "사용법"),
            ]
        )

    app.post_init = _set_commands

    print("텔레그램 봇 실행 중... (Ctrl+C 로 종료)")
    app.run_polling()


if __name__ == "__main__":
    main()
