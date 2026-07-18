"""자연어 여행 요청 → 구조화된 검색 조건 (Gemini API).

"다음 주 금요일에 오사카 갔다가 일요일에 오는 표, 30만원 밑이면 알려줘" 같은
문장을 Gemini가 의도(intent)와 조건(JSON)으로 변환합니다. 실제 항공권 검색은
기존 SerpApi 로직이 그대로 수행하므로 SerpApi 한도에는 영향이 없습니다.

무료 API 키: https://aistudio.google.com/apikey (Gemini API 무료 등급)
환경변수: GEMINI_API_KEY (필수), GEMINI_MODEL (기본 gemini-2.5-flash)
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

import requests


class NLParseError(RuntimeError):
    """자연어 해석 실패 (API 오류·응답 형식 오류)."""


_WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

INTENTS = {"search", "flex", "watch", "multi", "unknown"}


def _build_prompt(today: datetime) -> str:
    return f"""당신은 항공권 검색 텔레그램 봇의 파서입니다. 사용자의 한국어(또는 영어) 요청에서 검색 조건을 추출해 JSON 하나만 출력하세요. JSON 외 다른 텍스트는 절대 출력하지 마세요.

오늘 날짜: {today.strftime('%Y-%m-%d')} ({_WEEKDAYS_KO[today.weekday()]}요일)

JSON 스키마:
{{
  "intent": "search" | "flex" | "watch" | "multi" | "unknown",
  "origin": "출발 공항 IATA 코드 (예: ICN). 언급이 없으면 \\"ICN\\"",
  "destination": "도착 공항 IATA 코드 (예: KIX)",
  "departure_date": "YYYY-MM-DD",
  "return_date": "YYYY-MM-DD 또는 null(편도)",
  "legs": [["출발IATA", "도착IATA", "YYYY-MM-DD"], ...],
  "adults": 1,
  "non_stop": false,
  "travel_class": null,
  "target_price": null,
  "clarification": null
}}

규칙:
- intent 판단: 날짜가 대략적이거나 유연하면("~쯤", "근처", "아무 날이나", "싼 날") "flex". "떨어지면/싸지면/이하면 알려줘" 등 가격 알림 요청이면 "watch" (target_price 필수, "30만원"→300000). 경유지를 들르는 여정(도시 3곳 이상 이동)이면 "multi" (legs 채우기, 2~5개). 그 외 일반 검색은 "search".
- 상대 날짜("다음 주 금요일", "이번 주말", "8월 초")는 오늘 날짜 기준으로 YYYY-MM-DD로 계산. "8월 초"처럼 범위면 대표 날짜 하나 고르고 intent는 "flex".
- 도시→IATA 예: 서울/인천→ICN, 김포→GMP, 부산→PUS, 제주→CJU, 도쿄→NRT, 오사카→KIX, 후쿠오카→FUK, 삿포로→CTS, 오키나와→OKA, 방콕→BKK, 다낭→DAD, 하노이→HAN, 타이베이→TPE, 홍콩→HKG, 싱가포르→SIN, 파리→CDG, 런던→LHR, 뉴욕→JFK, LA→LAX. 확실하지 않은 도시는 해당 도시의 대표 국제공항 IATA를 아는 만큼 정확히.
- travel_class: 이코노미=null, 프리미엄 이코노미=2, 비즈니스=3, 일등석=4
- adults: 인원 언급 없으면 1. "둘이서/커플/부부"→2, "가족 4명"→4
- 목적지·날짜를 알 수 없거나, 날짜가 과거이거나, 항공권과 무관한 요청이면 intent="unknown"으로 하고 clarification에 사용자에게 물어볼 한국어 질문 한 문장을 넣으세요.
- 확실한 정보만 채우고, 추측이 심한 필드는 clarification으로 확인하세요."""


def extract_json(raw: str) -> dict:
    """모델 응답에서 JSON 객체를 꺼낸다 (```json 펜스나 앞뒤 잡담 허용)."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if not brace:
            raise NLParseError(f"응답에서 JSON을 찾지 못했습니다: {raw[:200]}")
        text = brace.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NLParseError(f"JSON 해석 실패: {exc}") from exc
    if not isinstance(data, dict):
        raise NLParseError("JSON 객체가 아닙니다.")
    return data


def _valid_date(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def coerce_request(data: dict, today: datetime | None = None) -> dict:
    """모델이 준 dict를 안전한 형태로 정규화. 문제가 있으면 intent=unknown."""
    today = today or datetime.now()
    req = {
        "intent": data.get("intent") if data.get("intent") in INTENTS else "unknown",
        "origin": None,
        "destination": None,
        "departure_date": None,
        "return_date": None,
        "legs": [],
        "adults": 1,
        "non_stop": bool(data.get("non_stop")),
        "travel_class": None,
        "target_price": None,
        "clarification": data.get("clarification") or None,
    }

    for key in ("origin", "destination"):
        value = data.get(key)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z]{3}", value.strip()):
            req[key] = value.strip().upper()

    if _valid_date(data.get("departure_date")):
        req["departure_date"] = data["departure_date"]
    if _valid_date(data.get("return_date")):
        req["return_date"] = data["return_date"]

    try:
        req["adults"] = max(1, min(9, int(data.get("adults") or 1)))
    except (TypeError, ValueError):
        pass
    if data.get("travel_class") in (2, 3, 4):
        req["travel_class"] = data["travel_class"]
    try:
        if data.get("target_price"):
            req["target_price"] = float(data["target_price"])
    except (TypeError, ValueError):
        pass

    legs = data.get("legs") or []
    if isinstance(legs, list):
        for leg in legs:
            if (
                isinstance(leg, (list, tuple)) and len(leg) == 3
                and isinstance(leg[0], str) and re.fullmatch(r"[A-Za-z]{3}", leg[0].strip())
                and isinstance(leg[1], str) and re.fullmatch(r"[A-Za-z]{3}", leg[1].strip())
                and _valid_date(leg[2])
            ):
                req["legs"].append((leg[0].strip().upper(), leg[1].strip().upper(), leg[2]))

    # 의도별 필수 정보 검증 - 부족하면 unknown으로 강등하고 질문 생성
    def _demote(question: str) -> None:
        req["intent"] = "unknown"
        if not req["clarification"]:
            req["clarification"] = question

    today_str = today.strftime("%Y-%m-%d")
    if req["intent"] in ("search", "flex", "watch"):
        if not (req["origin"] and req["destination"] and req["departure_date"]):
            _demote("어디에서 어디로, 언제 떠나는 항공권을 찾을까요?")
        elif req["departure_date"] < today_str:
            _demote("출발 날짜가 과거로 계산됐어요. 언제 출발하시나요?")
    if req["intent"] == "watch" and req["target_price"] is None:
        _demote("얼마 이하로 떨어지면 알려드릴까요? (예: 30만원)")
    if req["intent"] == "multi":
        if len(req["legs"]) < 2:
            _demote("다구간 여정의 구간별 출발지·도착지·날짜를 알려주세요.")
        elif any(d < today_str for _, _, d in req["legs"]):
            _demote("여정에 과거 날짜가 있어요. 날짜를 다시 알려주세요.")

    return req


def parse_travel_request(
    text: str,
    api_key: str,
    model: str | None = None,
    today: datetime | None = None,
    timeout: int = 30,
) -> dict:
    """자연어 요청을 Gemini로 해석해 정규화된 조건 dict를 반환."""
    if not api_key:
        raise NLParseError("GEMINI_API_KEY 가 설정되지 않았습니다.")
    model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    today = today or datetime.now()

    body = {
        "contents": [
            {"parts": [{"text": _build_prompt(today) + "\n\n사용자 요청: " + text}]}
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
        },
    }
    try:
        resp = requests.post(
            _ENDPOINT.format(model=model),
            params={"key": api_key},
            json=body,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise NLParseError(f"Gemini API 연결 실패: {exc}") from exc

    if resp.status_code != 200:
        raise NLParseError(f"Gemini API 오류 ({resp.status_code}): {resp.text[:300]}")

    try:
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise NLParseError(f"Gemini 응답 형식 오류: {resp.text[:300]}") from exc

    return coerce_request(extract_json(raw), today=today)


def describe_request(req: dict) -> str:
    """해석 결과를 사용자에게 확인시켜줄 한 줄 요약."""
    if req["intent"] == "multi":
        route = " → ".join([req["legs"][0][0]] + [d for _, d, _ in req["legs"]])
        return f"다구간 {route}"
    trip = req["departure_date"] + (f"~{req['return_date']}" if req["return_date"] else " 편도")
    base = f"{req['origin']}→{req['destination']} {trip}"
    extras = []
    if req["intent"] == "flex":
        extras.append("±3일 최저가 비교")
    if req["intent"] == "watch" and req["target_price"]:
        extras.append(f"{req['target_price']:,.0f}원 이하 알림")
    if req["non_stop"]:
        extras.append("직항만")
    if req["adults"] > 1:
        extras.append(f"성인 {req['adults']}명")
    if req["travel_class"]:
        extras.append({2: "프리미엄 이코노미", 3: "비즈니스", 4: "일등석"}[req["travel_class"]])
    return base + (" · " + " · ".join(extras) if extras else "")
