"""서버리스(웹훅)용 텔레그램 봇 로직 — 순수 requests 기반.

python-telegram-bot 의 async/폴링/JobQueue 없이, 텔레그램 Update(dict) 하나를
받아 처리하고 Bot API 로 답장합니다. Vercel 같은 서버리스 함수에서 호출합니다.

가격 알림(watch)은 항상 켜진 프로세스가 필요해 서버리스에서는 제외했습니다.
검색 기능만 제공합니다: /flight, /flex, /menu(버튼), /help
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import requests

from .formatter import format_flexible, format_results
from .search import search_flexible_dates, search_flights
from .serpapi_client import FlightSearchError, SerpApiClient
from .airports import resolve_airport

HELP_TEXT = (
    "✈️ 항공권 검색 봇\n\n"
    "검색:\n"
    "/flight 출발 도착 출발일 [귀국일]\n"
    "예) /flight 인천 후쿠오카 2026-06-06 2026-06-07\n"
    "(공항 이름은 한글로 입력해도 됩니다)\n\n"
    "날짜별 최저가 (±3일):\n"
    "/flex 출발 도착 기준출발일 [귀국일]\n\n"
    "버튼으로 검색: /menu"
)

_POPULAR = [
    ("인천", "ICN"), ("김포", "GMP"), ("부산", "PUS"), ("제주", "CJU"),
    ("후쿠오카", "FUK"), ("도쿄", "NRT"), ("오사카", "KIX"), ("삿포로", "CTS"),
    ("방콕", "BKK"), ("다낭", "DAD"), ("타이베이", "TPE"), ("홍콩", "HKG"),
]


# ---- 텔레그램 Bot API 호출 (순수 requests) ----------------------------

def _api(token: str, method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        resp = requests.post(url, json=payload, timeout=15)
        return resp.json()
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)}


def send_message(token: str, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    _api(token, "sendMessage", payload)


def edit_message(token: str, chat_id: int, message_id: int, text: str,
                 reply_markup: dict | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    _api(token, "editMessageText", payload)


def answer_callback(token: str, callback_id: str) -> None:
    _api(token, "answerCallbackQuery", {"callback_query_id": callback_id})


# ---- 입력 검증 --------------------------------------------------------

def _is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _client() -> SerpApiClient | None:
    key = os.getenv("SERPAPI_KEY", "")
    return SerpApiClient(api_key=key) if key else None


# ---- 버튼 키보드 ------------------------------------------------------

def _airport_keyboard(stage: str) -> dict:
    rows, row = [], []
    for name, code in _POPULAR:
        row.append({"text": name, "callback_data": f"{stage}:{code}"})
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows}


def _date_keyboard(stage: str, include_oneway: bool = False) -> dict:
    today = datetime.now().date()
    rows: list[list[dict]] = []
    if include_oneway:
        rows.append([{"text": "편도 (귀국 없음)", "callback_data": f"{stage}:oneway"}])
    row: list[dict] = []
    for offset in range(1, 15):
        d = today + timedelta(days=offset)
        row.append({"text": d.strftime("%m/%d"), "callback_data": f"{stage}:{d.isoformat()}"})
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows}


# ---- 명령어 처리 ------------------------------------------------------

def _handle_flight(token: str, chat_id: int, args: list[str]) -> None:
    client = _client()
    if client is None:
        send_message(token, chat_id, "서버에 SERPAPI_KEY 가 설정되지 않았습니다.")
        return
    if len(args) < 3:
        send_message(token, chat_id, HELP_TEXT)
        return
    try:
        origin = resolve_airport(args[0])
        destination = resolve_airport(args[1])
    except ValueError as exc:
        send_message(token, chat_id, str(exc))
        return

    departure_date = args[2]
    return_date = args[3] if len(args) >= 4 else None
    bad = [d for d in (departure_date, return_date) if d and not _is_valid_date(d)]
    if bad:
        send_message(token, chat_id, f"날짜 형식 오류: {', '.join(bad)} (YYYY-MM-DD)")
        return

    send_message(token, chat_id, "🔎 검색 중입니다...")
    try:
        offers = search_flights(
            origin=origin, destination=destination,
            departure_date=departure_date, return_date=return_date, client=client,
        )
    except FlightSearchError as exc:
        send_message(token, chat_id, f"검색 오류: {exc}")
        return
    send_message(token, chat_id,
                 format_results(offers, origin, destination, departure_date, return_date))


def _handle_flex(token: str, chat_id: int, args: list[str]) -> None:
    client = _client()
    if client is None:
        send_message(token, chat_id, "서버에 SERPAPI_KEY 가 설정되지 않았습니다.")
        return
    if len(args) < 3:
        send_message(token, chat_id,
                     "사용법: /flex 출발 도착 기준출발일 [귀국일]")
        return
    try:
        origin = resolve_airport(args[0])
        destination = resolve_airport(args[1])
    except ValueError as exc:
        send_message(token, chat_id, str(exc))
        return

    base_date = args[2]
    return_date = args[3] if len(args) >= 4 else None
    bad = [d for d in (base_date, return_date) if d and not _is_valid_date(d)]
    if bad:
        send_message(token, chat_id, f"날짜 형식 오류: {', '.join(bad)}")
        return

    send_message(token, chat_id, "📅 날짜별 최저가를 조사 중입니다... (조금 걸립니다)")
    try:
        results = search_flexible_dates(
            origin=origin, destination=destination, base_date=base_date,
            flex_days=3, return_date=return_date, client=client,
        )
    except FlightSearchError as exc:
        send_message(token, chat_id, f"검색 오류: {exc}")
        return
    send_message(token, chat_id, format_flexible(results, origin, destination))


# ---- 버튼(마법사) 처리 ------------------------------------------------
# 서버리스는 상태를 못 들고 있어서, 진행 상태를 callback_data 에 담아 전달합니다.
# 형식: stage:value|origin|dest|out  (필요한 만큼만 채워짐)

def _wiz_pack(stage: str, value: str, ctx: dict) -> str:
    parts = [f"{stage}:{value}", ctx.get("o", ""), ctx.get("d", ""), ctx.get("out", "")]
    return "|".join(parts)


def _handle_callback(token: str, query: dict) -> None:
    answer_callback(token, query["id"])
    data = query.get("data", "")
    msg = query["message"]
    chat_id = msg["chat"]["id"]
    message_id = msg["message_id"]

    head, _, rest = data.partition("|")
    stage, _, value = head.partition(":")
    o, d, out = (rest.split("|") + ["", "", ""])[:3]
    ctx = {"o": o, "d": d, "out": out}

    if stage == "origin":
        ctx["o"] = value
        edit_message(token, chat_id, message_id, f"출발: {value}\n도착지를 선택하세요",
                     _kbd_with_ctx("dest", _airport_keyboard("dest"), ctx))
    elif stage == "dest":
        ctx["d"] = value
        edit_message(token, chat_id, message_id,
                     f"{ctx['o']} → {value}\n출발일을 선택하세요",
                     _kbd_with_ctx("out", _date_keyboard("out"), ctx))
    elif stage == "out":
        ctx["out"] = value
        edit_message(token, chat_id, message_id,
                     f"{ctx['o']} → {ctx['d']}\n출발일 {value}\n귀국일 선택 (편도 가능)",
                     _kbd_with_ctx("ret", _date_keyboard("ret", include_oneway=True), ctx))
    elif stage == "ret":
        ret = None if value == "oneway" else value
        client = _client()
        if client is None:
            edit_message(token, chat_id, message_id, "서버에 SERPAPI_KEY 가 없습니다.")
            return
        edit_message(token, chat_id, message_id, "🔎 검색 중입니다...")
        try:
            offers = search_flights(origin=ctx["o"], destination=ctx["d"],
                                    departure_date=ctx["out"], return_date=ret, client=client)
        except FlightSearchError as exc:
            edit_message(token, chat_id, message_id, f"검색 오류: {exc}")
            return
        edit_message(token, chat_id, message_id,
                     format_results(offers, ctx["o"], ctx["d"], ctx["out"], ret))


def _kbd_with_ctx(stage: str, keyboard: dict, ctx: dict) -> dict:
    """키보드의 모든 버튼 callback_data 에 진행 컨텍스트(o|d|out)를 덧붙인다."""
    suffix = "|".join([ctx.get("o", ""), ctx.get("d", ""), ctx.get("out", "")])
    new_rows = []
    for row in keyboard["inline_keyboard"]:
        new_row = []
        for btn in row:
            new_row.append({"text": btn["text"], "callback_data": f"{btn['callback_data']}|{suffix}"})
        new_rows.append(new_row)
    return {"inline_keyboard": new_rows}


# ---- 진입점 -----------------------------------------------------------

def handle_update(update: dict, token: str) -> None:
    """텔레그램 Update(dict) 하나를 처리한다. (서버리스 함수가 호출)"""
    if "callback_query" in update:
        _handle_callback(token, update["callback_query"])
        return

    message = update.get("message") or update.get("edited_message")
    if not message or "text" not in message:
        return

    chat_id = message["chat"]["id"]
    text = message["text"].strip()
    if not text.startswith("/"):
        send_message(token, chat_id, HELP_TEXT)
        return

    parts = text.split()
    command = parts[0].split("@")[0].lower()  # /flight@MyBot -> /flight
    args = parts[1:]

    if command in ("/start", "/help"):
        send_message(token, chat_id, HELP_TEXT)
    elif command == "/flight":
        _handle_flight(token, chat_id, args)
    elif command == "/flex":
        _handle_flex(token, chat_id, args)
    elif command == "/menu":
        send_message(token, chat_id, "출발지를 선택하세요 ✈️", _airport_keyboard("origin"))
    else:
        send_message(token, chat_id, HELP_TEXT)
