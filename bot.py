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

import asyncio
import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from flightchecker import (
    FlightSearchError,
    PriceHistory,
    SerpApiClient,
    Watch,
    WatchStore,
    cheapest_price,
    describe_options,
    google_flights_url,
    parse_search_options,
    resolve_airport,
    search_flexible_dates,
    search_flights,
    search_multi_city,
    skyscanner_url,
)
from flightchecker.formatter import format_flexible, format_multi, format_results
from flightchecker.nlsearch import NLParseError, describe_request, parse_travel_request

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "✈️ *항공권 검색 봇*\n\n"
    "*🤖 그냥 문장으로 보내도 됩니다*\n"
    "예) `다음 주 금요일에 오사카 갔다가 일요일에 오는 표`\n"
    "예) `방콕 왕복 30만원 밑으로 떨어지면 알려줘`\n\n"
    "*검색*\n"
    "`/flight 출발 도착 출발일 [귀국일]`\n"
    "예) `/flight 인천 후쿠오카 2026-06-06 2026-06-07`\n"
    "(공항 이름은 한글로 입력해도 됩니다)\n\n"
    "*옵션* — 명령 뒤에 붙이면 됩니다\n"
    "`2명` `비즈니스` `일등석` `경유포함`\n"
    "예) `/flight 인천 방콕 2026-06-06 2명 비즈니스`\n"
    "※ 항상 직항만 검색합니다 (경유도 보려면 `경유포함` 추가)\n\n"
    "*날짜별 최저가* (±3일 비교)\n"
    "`/flex 출발 도착 기준출발일 [귀국일]`\n\n"
    "*다구간* — 출발 도착 날짜를 구간 수만큼 반복\n"
    "`/multi 인천 도쿄 2026-06-06 도쿄 오사카 2026-06-08 오사카 인천 2026-06-10`\n\n"
    "*가격 알림*\n"
    "`/watch 출발 도착 출발일 [귀국일] 목표가`\n"
    "예) `/watch 인천 후쿠오카 2026-06-06 2026-06-07 200000`\n"
    "목표가 이하로 떨어지면 자동으로 알려줍니다.\n"
    "평소보다 20% 이상 급락해도 알려줍니다. 📉\n"
    "`/watches` 목록 · `/unwatch 번호` 삭제\n\n"
    "*가격 그래프*: `/history` — 알림 노선의 가격 변화 📈\n\n"
    "*버튼으로 검색*: /menu"
)

# 가격 알림 검사 주기(초). 기본 6시간.
WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL_SEC", str(6 * 3600)))
# 급락 감지: 최근 평균 대비 이만큼(%) 이상 싸지면 알림
DROP_ALERT_PCT = float(os.getenv("DROP_ALERT_PCT", "20"))
# 같은 노선 급락 알림 최소 간격(시간)
DROP_ALERT_COOLDOWN_H = float(os.getenv("DROP_ALERT_COOLDOWN_H", "24"))

_api_key = os.getenv("SERPAPI_KEY", "")
_client = SerpApiClient(api_key=_api_key) if _api_key else None
_store = WatchStore()
_history = PriceHistory()
# 자연어 검색(선택 기능). https://aistudio.google.com/apikey 에서 무료 발급
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")


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


# ---- 검색 결과에 붙는 버튼 --------------------------------------------

def _booking_buttons(origin: str, dest: str, dep: str, ret: str | None) -> list:
    """구글 항공권·스카이스캐너로 바로 가는 예매 링크 버튼 한 줄."""
    from telegram import InlineKeyboardButton

    return [
        InlineKeyboardButton("🛒 구글 항공권", url=google_flights_url(origin, dest, dep, ret)),
        InlineKeyboardButton("🛒 스카이스캐너", url=skyscanner_url(origin, dest, dep, ret)),
    ]


def _booking_keyboard(origin: str, dest: str, dep: str, ret: str | None):
    from telegram import InlineKeyboardMarkup

    return InlineKeyboardMarkup([_booking_buttons(origin, dest, dep, ret)])


def _result_keyboard(origin: str, dest: str, dep: str, ret: str | None, price: float | None):
    """검색 결과 메시지 아래에 붙는 버튼: 예매 링크 + 알림 등록 + 가격 이력."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    ret_token = ret or "-"
    rows = [_booking_buttons(origin, dest, dep, ret)]
    if price:
        row = []
        for pct in (5, 10):
            target = int(price * (100 - pct) / 100 // 100 * 100)  # 100원 단위 절사
            row.append(
                InlineKeyboardButton(
                    f"🔔 알림 -{pct}% ({target:,})",
                    callback_data=f"aw:{origin}:{dest}:{dep}:{ret_token}:{target}",
                )
            )
        rows.append(row)
    rows.append(
        [InlineKeyboardButton("📈 가격 이력 보기", callback_data=f"hist:{origin}:{dest}:{dep}:{ret_token}")]
    )
    return InlineKeyboardMarkup(rows)


# ---- 명령어 핸들러 ----------------------------------------------------

async def start_command(update, context):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def flight_command(update, context):
    if _client is None:
        await update.message.reply_text("서버에 SERPAPI_KEY 가 설정되지 않았습니다.")
        return

    args, opts = parse_search_options(context.args)
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
            non_stop=opts["non_stop"],
            adults=opts["adults"],
            travel_class=opts["travel_class"],
            client=_client,
        )
    except FlightSearchError as exc:
        await update.message.reply_text(f"검색 오류: {exc}")
        return

    price = cheapest_price(offers)
    # 기본 조건(1명/이코노미) 검색만 이력에 기록 - 그래프·급락 감지 기준을 일정하게 유지
    if opts["adults"] == 1 and not opts["travel_class"]:
        _history.record(origin, destination, departure_date, return_date, price)

    text = format_results(offers, origin, destination, departure_date, return_date)
    opt_note = describe_options(opts)
    if opt_note:
        text = f"⚙ {opt_note}\n{text}"
    if not offers and opts["non_stop"]:
        text += "\n\n💡 직항만 검색했습니다. 경유도 보려면 명령 뒤에 `경유포함` 을 붙여보세요."
    await update.message.reply_text(
        text,
        reply_markup=_result_keyboard(origin, destination, departure_date, return_date, price),
    )


async def flex_command(update, context):
    if _client is None:
        await update.message.reply_text("서버에 SERPAPI_KEY 가 설정되지 않았습니다.")
        return

    args, opts = parse_search_options(context.args)
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
            non_stop=opts["non_stop"],
            adults=opts["adults"],
            travel_class=opts["travel_class"],
            client=_client,
        )
    except FlightSearchError as exc:
        await update.message.reply_text(f"검색 오류: {exc}")
        return

    # 날짜별 최저가도 이력에 기록 (기본 조건 검색만)
    if opts["adults"] == 1 and not opts["travel_class"]:
        for out_date, ret_date, price in results:
            _history.record(origin, destination, out_date, ret_date, price)

    text = format_flexible(results, origin, destination)
    opt_note = describe_options(opts)
    if opt_note:
        text = f"⚙ {opt_note}\n{text}"
    await update.message.reply_text(text)


MULTI_USAGE = (
    "사용법: /multi 출발 도착 날짜 출발 도착 날짜 ...  (2~5개 구간)\n"
    "예) /multi 인천 도쿄 2026-06-06 도쿄 오사카 2026-06-08 오사카 인천 2026-06-10\n"
    "옵션도 됩니다: 직항 2명 비즈니스"
)


async def multi_command(update, context):
    if _client is None:
        await update.message.reply_text("서버에 SERPAPI_KEY 가 설정되지 않았습니다.")
        return

    args, opts = parse_search_options(context.args)
    if len(args) < 6 or len(args) % 3 != 0:
        await update.message.reply_text(MULTI_USAGE)
        return

    chunks = [args[i:i + 3] for i in range(0, len(args), 3)]
    if len(chunks) > 5:
        await update.message.reply_text("구간은 최대 5개까지 가능합니다.")
        return

    legs: list[tuple[str, str, str]] = []
    for leg_origin, leg_dest, leg_date in chunks:
        try:
            origin, destination = _resolve_pair(leg_origin, leg_dest)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        if not _is_valid_date(leg_date):
            await update.message.reply_text(f"날짜 형식 오류: {leg_date} (YYYY-MM-DD 로 입력)")
            return
        legs.append((origin, destination, leg_date))

    # 구간 날짜가 순서대로인지 확인
    dates = [d for _, _, d in legs]
    if dates != sorted(dates):
        await update.message.reply_text("구간 날짜가 순서대로가 아닙니다. 이동 순서대로 입력해 주세요.")
        return

    await update.message.reply_text(f"🔎 다구간 {len(legs)}개 구간을 검색 중입니다...")
    try:
        offers = search_multi_city(
            legs,
            non_stop=opts["non_stop"],
            adults=opts["adults"],
            travel_class=opts["travel_class"],
            client=_client,
        )
    except FlightSearchError as exc:
        await update.message.reply_text(f"검색 오류: {exc}")
        return

    text = format_multi(offers, legs)
    opt_note = describe_options(opts)
    if opt_note:
        text = f"⚙ {opt_note}\n{text}"
    await update.message.reply_text(text)


async def watch_command(update, context):
    args, opts = parse_search_options(context.args)
    if len(args) < 4:
        await update.message.reply_text(
            "사용법: /watch 출발 도착 출발일 [귀국일] 목표가\n"
            "예) /watch 인천 후쿠오카 2026-06-06 2026-06-07 200000\n"
            "옵션도 됩니다: /watch 인천 방콕 2026-06-06 직항 300000"
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
        non_stop=opts["non_stop"],
        adults=opts["adults"],
        travel_class=opts["travel_class"],
    )
    if _store.add(watch):
        trip = f"{departure_date}~{return_date}" if return_date else departure_date
        opt_note = describe_options(opts)
        await update.message.reply_text(
            f"🔔 알림 등록 완료\n{origin}→{destination} {trip}"
            + (f" ({opt_note})" if opt_note else "")
            + f"\n목표가 {target_price:,.0f} KRW 이하가 되면 알려드릴게요.\n"
            f"평소보다 {DROP_ALERT_PCT:.0f}% 이상 급락해도 알려드립니다. 📉\n"
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
        opt_note = describe_options(
            {"non_stop": w.non_stop, "adults": w.adults, "travel_class": w.travel_class}
        )
        lines.append(
            f"{i}. {w.origin}→{w.destination} {trip} · 목표 {w.target_price:,.0f} KRW{last}"
            + (f" · {opt_note}" if opt_note else "")
        )
    lines.append("\n삭제: /unwatch 번호 · 가격 그래프: /history 번호")
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


# ---- 자연어 검색 (Gemini) ---------------------------------------------

async def ai_command(update, context):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text(
            "사용법: /ai 원하는 걸 문장으로\n"
            "예) /ai 다음 주 금요일에 오사카 갔다가 일요일에 오는 표\n"
            "(명령어 없이 그냥 문장을 보내도 됩니다)"
        )
        return
    await _handle_ai_text(update, context, text)


async def on_text(update, context):
    """명령어가 아닌 일반 문장 → 자연어 검색으로 처리."""
    text = (update.message.text or "").strip()
    if not text:
        return
    if not GEMINI_KEY:
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")
        return
    await _handle_ai_text(update, context, text)


async def _handle_ai_text(update, context, text: str):
    if not GEMINI_KEY:
        await update.message.reply_text(
            "서버에 GEMINI_API_KEY 가 설정되지 않아 자연어 검색을 쓸 수 없습니다.\n"
            "https://aistudio.google.com/apikey 에서 무료 발급 후 환경변수에 추가하세요."
        )
        return
    if _client is None:
        await update.message.reply_text("서버에 SERPAPI_KEY 가 설정되지 않았습니다.")
        return

    await update.message.reply_text("🤖 요청을 이해하는 중입니다...")
    try:
        req = await asyncio.to_thread(parse_travel_request, text, GEMINI_KEY)
    except NLParseError as exc:
        logger.warning("자연어 해석 실패: %s", exc)
        await update.message.reply_text(
            "요청을 이해하지 못했습니다. 조금 더 구체적으로 말씀해 주시거나 /help 명령어를 참고하세요.\n"
            f"(원인: {str(exc)[:250]})"
        )
        return

    if req["intent"] == "unknown":
        await update.message.reply_text(
            "🤖 " + (req["clarification"] or "어디에서 어디로, 언제 가는 항공권을 찾을까요?")
        )
        return

    summary = describe_request(req)
    opts = {
        "non_stop": req["non_stop"],
        "adults": req["adults"],
        "travel_class": req["travel_class"],
    }

    # 가격 알림 등록은 검색 없이 바로 처리 (SerpApi 호출 절약)
    if req["intent"] == "watch":
        watch = Watch(
            chat_id=update.effective_chat.id,
            origin=req["origin"],
            destination=req["destination"],
            departure_date=req["departure_date"],
            return_date=req["return_date"],
            target_price=req["target_price"],
            non_stop=req["non_stop"],
            adults=req["adults"],
            travel_class=req["travel_class"],
        )
        if _store.add(watch):
            await update.message.reply_text(
                f"🤖 이렇게 이해했어요: {summary}\n\n"
                f"🔔 알림 등록 완료! 목표가 이하가 되면 알려드릴게요.\n"
                f"평소보다 {DROP_ALERT_PCT:.0f}% 이상 급락해도 알려드립니다. 📉\n"
                f"(약 {WATCH_INTERVAL // 3600}시간마다 자동 확인 · 목록 /watches)"
            )
        else:
            await update.message.reply_text("이미 같은 조건의 알림이 등록되어 있습니다.")
        return

    await update.message.reply_text(f"🤖 이렇게 이해했어요: {summary}\n🔎 검색 중입니다...")
    try:
        if req["intent"] == "flex":
            results = await asyncio.to_thread(
                search_flexible_dates,
                origin=req["origin"],
                destination=req["destination"],
                base_date=req["departure_date"],
                flex_days=3,
                return_date=req["return_date"],
                non_stop=opts["non_stop"],
                adults=opts["adults"],
                travel_class=opts["travel_class"],
                client=_client,
            )
            if opts["adults"] == 1 and not opts["travel_class"]:
                for out_date, ret_date, price in results:
                    _history.record(req["origin"], req["destination"], out_date, ret_date, price)
            await update.message.reply_text(
                format_flexible(results, req["origin"], req["destination"])
            )
        elif req["intent"] == "multi":
            offers = await asyncio.to_thread(
                search_multi_city,
                req["legs"],
                non_stop=opts["non_stop"],
                adults=opts["adults"],
                travel_class=opts["travel_class"],
                client=_client,
            )
            await update.message.reply_text(format_multi(offers, req["legs"]))
        else:  # search
            offers = await asyncio.to_thread(
                search_flights,
                origin=req["origin"],
                destination=req["destination"],
                departure_date=req["departure_date"],
                return_date=req["return_date"],
                non_stop=opts["non_stop"],
                adults=opts["adults"],
                travel_class=opts["travel_class"],
                client=_client,
            )
            price = cheapest_price(offers)
            if opts["adults"] == 1 and not opts["travel_class"]:
                _history.record(
                    req["origin"], req["destination"],
                    req["departure_date"], req["return_date"], price,
                )
            text = format_results(
                offers, req["origin"], req["destination"],
                req["departure_date"], req["return_date"],
            )
            if not offers and opts["non_stop"]:
                text += "\n\n💡 직항만 검색했습니다. 경유도 보고 싶으면 \"경유 포함해서\" 라고 말해보세요."
            await update.message.reply_text(
                text,
                reply_markup=_result_keyboard(
                    req["origin"], req["destination"],
                    req["departure_date"], req["return_date"], price,
                ),
            )
    except FlightSearchError as exc:
        await update.message.reply_text(f"검색 오류: {exc}")


# ---- 가격 이력 그래프 --------------------------------------------------

async def history_command(update, context):
    """알림 등록한 노선의 가격 변화 그래프를 이미지로 전송."""
    chat_id = update.effective_chat.id
    items = _store.list_for(chat_id)
    if not items:
        await update.message.reply_text(
            "등록된 가격 알림이 없습니다.\n"
            "/watch 로 알림을 등록하면 가격 이력이 자동으로 쌓이고,\n"
            "/history 로 그래프를 볼 수 있습니다."
        )
        return

    args = context.args
    if args and args[0].isdigit():
        index = int(args[0])
    elif len(items) == 1:
        index = 1
    else:
        lines = ["📈 어느 노선의 그래프를 볼까요? /history 번호 로 선택하세요:"]
        for i, w in enumerate(items, start=1):
            trip = f"{w.departure_date}~{w.return_date}" if w.return_date else w.departure_date
            lines.append(f"{i}. {w.origin}→{w.destination} {trip}")
        await update.message.reply_text("\n".join(lines))
        return

    if index < 1 or index > len(items):
        await update.message.reply_text("해당 번호의 알림을 찾을 수 없습니다. /watches 로 확인하세요.")
        return

    w = items[index - 1]
    await _send_history_chart(
        context.bot, chat_id, w.origin, w.destination,
        w.departure_date, w.return_date, target_price=w.target_price,
    )


async def _send_history_chart(bot, chat_id, origin, dest, dep, ret, target_price=None):
    """가격 이력이 충분하면 그래프 전송, 아니면 안내 메시지."""
    points = _history.series(origin, dest, dep, ret)
    trip = f"{dep}~{ret}" if ret else dep
    if len(points) < 2:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"📈 {origin}→{dest} {trip}\n"
                f"아직 가격 기록이 {len(points)}개뿐입니다.\n"
                "검색하거나 알림이 자동 확인될 때마다 기록이 쌓입니다. 나중에 다시 확인해 주세요!"
            ),
        )
        return

    from flightchecker.chart import render_price_chart

    title = f"{origin} -> {dest}  ({dep}" + (f" ~ {ret})" if ret else ")")
    png = render_price_chart(points, title, target_price=target_price)
    low = min(p for _, p in points)
    await bot.send_photo(
        chat_id=chat_id,
        photo=png,
        caption=(
            f"📈 {origin}→{dest} {trip}\n"
            f"기록 {len(points)}개 · 역대 최저 {low:,.0f} KRW"
            + (f" · 목표 {target_price:,.0f} KRW" if target_price else "")
        ),
    )


# ---- 가격 알림 주기 검사 (JobQueue) -----------------------------------

def _drop_cooldown_passed(w: Watch) -> bool:
    """급락 알림을 다시 보내도 될 만큼 시간이 지났는지."""
    if not w.last_drop_alert:
        return True
    try:
        last = datetime.fromisoformat(w.last_drop_alert)
    except ValueError:
        return True
    return datetime.now() - last >= timedelta(hours=DROP_ALERT_COOLDOWN_H)


async def check_watches(context):
    """등록된 모든 watch를 검사해 목표가 도달·가격 급락 시 알림."""
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
                adults=w.adults,
                travel_class=w.travel_class,
                client=_client,
            )
        except Exception as exc:
            logger.warning("watch 검사 실패 %s: %s", w.key, exc)
            continue

        price = cheapest_price(offers)
        # 급락 판단 기준(최근 평균)은 이번 가격을 기록하기 전에 계산
        baseline = _history.baseline(w.origin, w.destination, w.departure_date, w.return_date)
        if w.adults == 1 and not w.travel_class:
            _history.record(w.origin, w.destination, w.departure_date, w.return_date, price)
        w.last_price = price
        trip = f"{w.departure_date}~{w.return_date}" if w.return_date else w.departure_date
        keyboard = _booking_keyboard(w.origin, w.destination, w.departure_date, w.return_date)

        if price is not None and price <= w.target_price and not w.notified:
            w.notified = True
            await context.bot.send_message(
                chat_id=w.chat_id,
                text=(
                    f"🎉 가격 알림!\n{w.origin}→{w.destination} {trip}\n"
                    f"현재 최저가 {price:,.0f} KRW (목표 {w.target_price:,.0f} 이하)\n\n"
                    f"자세히: /flight {w.origin} {w.destination} {w.departure_date}"
                    + (f" {w.return_date}" if w.return_date else "")
                ),
                reply_markup=keyboard,
            )
        elif price is not None and price > w.target_price:
            # 다시 올라가면 알림 재무장
            w.notified = False

        # 급락 감지: 목표가와 무관하게, 최근 평균보다 크게 싸지면 알림
        if (
            price is not None
            and baseline
            and price <= baseline * (1 - DROP_ALERT_PCT / 100)
            and _drop_cooldown_passed(w)
        ):
            w.last_drop_alert = datetime.now().isoformat(timespec="seconds")
            drop_pct = (1 - price / baseline) * 100
            await context.bot.send_message(
                chat_id=w.chat_id,
                text=(
                    f"📉 가격 급락 감지!\n{w.origin}→{w.destination} {trip}\n"
                    f"최근 평균 {baseline:,.0f} KRW → 현재 {price:,.0f} KRW ({drop_pct:.0f}%↓)\n"
                    f"그래프: /history"
                ),
                reply_markup=keyboard,
            )
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

    if stage == "aw":
        # 검색 결과의 "알림 등록" 버튼: aw:출발:도착:출발일:귀국일|-:목표가
        await _register_watch_from_button(query, value)
        return
    if stage == "hist":
        # 검색 결과의 "가격 이력" 버튼: hist:출발:도착:출발일:귀국일|-
        parts = value.split(":")
        if len(parts) == 4:
            origin, dest, dep, ret = parts
            await _send_history_chart(
                query.get_bot(), query.message.chat_id,
                origin, dest, dep, None if ret == "-" else ret,
            )
        return

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


async def _register_watch_from_button(query, value: str) -> None:
    """검색 결과의 '알림 -N%' 버튼으로 watch를 즉시 등록."""
    parts = value.split(":")
    if len(parts) != 5:
        return
    origin, dest, dep, ret_token, target_str = parts
    ret = None if ret_token == "-" else ret_token
    try:
        target_price = float(target_str)
    except ValueError:
        return

    watch = Watch(
        chat_id=query.message.chat_id,
        origin=origin,
        destination=dest,
        departure_date=dep,
        return_date=ret,
        target_price=target_price,
    )
    trip = f"{dep}~{ret}" if ret else dep
    if _store.add(watch):
        await query.message.reply_text(
            f"🔔 알림 등록 완료\n{origin}→{dest} {trip}\n"
            f"목표가 {target_price:,.0f} KRW 이하가 되면 알려드릴게요.\n"
            f"평소보다 {DROP_ALERT_PCT:.0f}% 이상 급락해도 알려드립니다. 📉\n"
            f"(약 {WATCH_INTERVAL // 3600}시간마다 자동 확인 · 목록 /watches)"
        )
    else:
        await query.message.reply_text("이미 같은 조건의 알림이 등록되어 있습니다.")


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
    price = cheapest_price(offers)
    _history.record(origin, dest, out, ret, price)
    await query.edit_message_text(
        format_results(offers, origin, dest, out, ret),
        reply_markup=_result_keyboard(origin, dest, out, ret, price),
    )


async def error_handler(update, context):
    logger.error("처리 중 예외 발생", exc_info=context.error)
    if update and getattr(update, "message", None):
        err = context.error
        detail = f"{type(err).__name__}: {err}" if err else "원인 미상"
        await update.message.reply_text(
            "처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.\n"
            f"(오류: {detail[:250]})"
        )


def main() -> None:
    from telegram import BotCommand
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        MessageHandler,
        filters,
    )

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(".env 에 TELEGRAM_BOT_TOKEN 을 설정하세요.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler("flight", flight_command))
    app.add_handler(CommandHandler("flex", flex_command))
    app.add_handler(CommandHandler("multi", multi_command))
    app.add_handler(CommandHandler("watch", watch_command))
    app.add_handler(CommandHandler("watches", watches_command))
    app.add_handler(CommandHandler("unwatch", unwatch_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("ai", ai_command))
    # 명령어가 아닌 일반 문장은 자연어 검색으로
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_error_handler(error_handler)

    # 가격 알림 주기 검사
    if app.job_queue:
        app.job_queue.run_repeating(check_watches, interval=WATCH_INTERVAL, first=30)

    async def _set_commands(application):
        await application.bot.set_my_commands(
            [
                BotCommand("flight", "항공권 검색"),
                BotCommand("ai", "자연어로 검색 🤖"),
                BotCommand("flex", "날짜별 최저가 (±3일)"),
                BotCommand("multi", "다구간 검색"),
                BotCommand("watch", "가격 알림 등록"),
                BotCommand("watches", "내 알림 목록"),
                BotCommand("unwatch", "알림 삭제"),
                BotCommand("history", "가격 이력 그래프"),
                BotCommand("menu", "버튼으로 검색"),
                BotCommand("help", "사용법"),
            ]
        )

    app.post_init = _set_commands

    print("텔레그램 봇 실행 중... (Ctrl+C 로 종료)")
    app.run_polling()


if __name__ == "__main__":
    main()
