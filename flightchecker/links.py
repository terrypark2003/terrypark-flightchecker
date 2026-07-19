"""예매 사이트로 바로 가는 딥링크 생성.

SerpApi의 예약 옵션 API(booking_token)는 검색 1회를 추가로 소모하므로,
API 호출 없이 노선/날짜가 미리 채워진 검색 URL을 만들어 제공합니다.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

# 대한항공 보너스 좌석 조회 (노선/날짜 딥링크는 지원되지 않아 조회 페이지로 연결)
KOREAN_AIR_AWARD_URL = "https://www.koreanair.com/skypass/use-miles/award-availability"


def google_flights_url(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
) -> str:
    """구글 항공권 검색이 해당 노선/날짜로 바로 열리는 URL."""
    query = f"Flights from {origin} to {destination} on {departure_date}"
    if return_date:
        query += f" through {return_date}"
    return "https://www.google.com/travel/flights?q=" + quote(query)


def skyscanner_url(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
) -> str:
    """스카이스캐너(한국) 검색이 해당 노선/날짜로 바로 열리는 URL."""

    def _short(date_str: str) -> str:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%y%m%d")

    path = f"{origin.lower()}/{destination.lower()}/{_short(departure_date)}"
    if return_date:
        path += f"/{_short(return_date)}"
    return f"https://www.skyscanner.co.kr/transport/flights/{path}/"
