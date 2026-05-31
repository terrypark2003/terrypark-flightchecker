"""고수준 검색 함수 - CLI와 텔레그램 봇이 공통으로 호출하는 진입점.

이 모듈의 search_flights()만 알면 어디서든 항공권을 검색할 수 있습니다.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .models import FlightOffer
from .serpapi_client import SerpApiClient

load_dotenv()


def _build_client() -> SerpApiClient:
    return SerpApiClient(api_key=os.getenv("SERPAPI_KEY", ""))


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    adults: int = 1,
    currency: str = "KRW",
    non_stop: bool = False,
    limit: int = 10,
    client: SerpApiClient | None = None,
) -> list[FlightOffer]:
    """항공권을 검색해 가격 오름차순으로 정렬된 FlightOffer 리스트 반환.

    예)
        search_flights("ICN", "FUK", "2026-06-06", "2026-06-07")

    client를 직접 주입할 수 있어 봇에서는 클라이언트를 재사용할 수 있습니다.
    """
    client = client or _build_client()
    raw = client.flight_offers(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        adults=adults,
        currency=currency,
        non_stop=non_stop,
    )

    # SerpApi는 추천 항공편(best_flights)과 그 외(other_flights)로 나눠 반환
    raw_offers = raw.get("best_flights", []) + raw.get("other_flights", [])
    is_round_trip = bool(return_date)

    offers = [
        FlightOffer.from_api(o, currency=currency, is_round_trip=is_round_trip)
        for o in raw_offers
    ]
    offers.sort(key=lambda o: o.price if o.price else float("inf"))
    return offers[:limit]
