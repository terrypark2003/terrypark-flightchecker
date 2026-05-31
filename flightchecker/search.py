"""고수준 검색 함수 - CLI와 텔레그램 봇이 공통으로 호출하는 진입점.

이 모듈의 search_flights()만 알면 어디서든 항공권을 검색할 수 있습니다.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .amadeus_client import AmadeusClient
from .models import FlightOffer

load_dotenv()


def _build_client() -> AmadeusClient:
    return AmadeusClient(
        client_id=os.getenv("AMADEUS_CLIENT_ID", ""),
        client_secret=os.getenv("AMADEUS_CLIENT_SECRET", ""),
        env=os.getenv("AMADEUS_ENV", "test"),
    )


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    adults: int = 1,
    currency: str = "KRW",
    non_stop: bool = False,
    max_results: int = 10,
    client: AmadeusClient | None = None,
) -> list[FlightOffer]:
    """항공권을 검색해 가격 오름차순으로 정렬된 FlightOffer 리스트 반환.

    예)
        search_flights("ICN", "FUK", "2026-06-06", "2026-06-07")

    client를 직접 주입할 수 있어 봇에서는 토큰 캐시를 위해 클라이언트를
    재사용할 수 있습니다.
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
        max_results=max_results,
    )

    # 항공사 코드 -> 이름 사전 (응답의 dictionaries에 포함됨)
    carrier_names = raw.get("dictionaries", {}).get("carriers", {})

    offers = [FlightOffer.from_api(o, carrier_names) for o in raw.get("data", [])]
    offers.sort(key=lambda o: o.price)
    return offers
