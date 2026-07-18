"""고수준 검색 함수 - CLI와 텔레그램 봇이 공통으로 호출하는 진입점.

이 모듈의 search_flights()만 알면 어디서든 항공권을 검색할 수 있습니다.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from .models import FlightOffer
from .serpapi_client import SerpApiClient

load_dotenv()


def _build_client() -> SerpApiClient:
    return SerpApiClient(api_key=os.getenv("SERPAPI_KEY", ""))


# 이 시간(분) 이상 걸리는 장거리 노선은 경유 편도 함께 보여줌
LONGHAUL_MINUTES = int(float(os.getenv("LONGHAUL_MIN_HOURS", "10")) * 60)


def sort_offers(offers: list[FlightOffer]) -> list[FlightOffer]:
    """직항 우선 + 가격 오름차순 정렬.

    직항 그룹이 먼저 오고, 각 그룹 안에서는 싼 순서입니다.
    (경유가 함께 표시되는 장거리 노선에서도 직항이 항상 위)
    """
    return sorted(
        offers,
        key=lambda o: (0 if o.stops == 0 else 1, o.price if o.price else float("inf")),
    )


def drop_layovers(offers: list[FlightOffer]) -> list[FlightOffer]:
    """경유 제외 정책.

    - 직항이 있는 노선: 직항만 남김 (경유 제거)
    - 단, 직항 소요가 LONGHAUL_MINUTES(기본 10시간) 이상인 장거리는 경유도 유지
    - 직항이 아예 없는 노선(대부분 장거리): 경유 그대로 유지
    """
    non_stop = [o for o in offers if o.stops == 0]
    if not non_stop:
        return offers
    fastest = min((o.duration_minutes for o in non_stop if o.duration_minutes), default=0)
    if fastest and fastest >= LONGHAUL_MINUTES:
        return offers
    return non_stop


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    adults: int = 1,
    currency: str = "KRW",
    non_stop: bool = False,
    travel_class: int | None = None,
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
        travel_class=travel_class,
    )

    # SerpApi는 추천 항공편(best_flights)과 그 외(other_flights)로 나눠 반환
    raw_offers = raw.get("best_flights", []) + raw.get("other_flights", [])
    is_round_trip = bool(return_date)

    offers = [
        FlightOffer.from_api(o, currency=currency, is_round_trip=is_round_trip)
        for o in raw_offers
    ]
    offers = sort_offers(drop_layovers(offers))
    return offers[:limit]


def search_multi_city(
    legs: list[tuple[str, str, str]],
    adults: int = 1,
    currency: str = "KRW",
    non_stop: bool = False,
    travel_class: int | None = None,
    limit: int = 10,
    client: SerpApiClient | None = None,
) -> list[FlightOffer]:
    """다구간 항공권 검색. legs: [(출발, 도착, 날짜), ...] (2~5개 구간)

    SerpApi 다구간 응답은 왕복처럼 첫 구간 여정 + 전체 총액을 주므로,
    표시되는 일정은 첫 구간 기준이고 가격은 전체 여정 총액입니다.
    """
    client = client or _build_client()
    raw = client.multi_city_offers(
        legs=legs,
        adults=adults,
        currency=currency,
        non_stop=non_stop,
        travel_class=travel_class,
    )
    raw_offers = raw.get("best_flights", []) + raw.get("other_flights", [])
    offers = [FlightOffer.from_api(o, currency=currency) for o in raw_offers]
    offers = sort_offers(drop_layovers(offers))
    return offers[:limit]


def cheapest_price(offers: list[FlightOffer]) -> float | None:
    """오퍼 목록에서 최저가를 반환 (없으면 None)."""
    prices = [o.price for o in offers if o.price]
    return min(prices) if prices else None


def search_flexible_dates(
    origin: str,
    destination: str,
    base_date: str,
    flex_days: int = 3,
    return_date: str | None = None,
    trip_length: int | None = None,
    currency: str = "KRW",
    non_stop: bool = False,
    adults: int = 1,
    travel_class: int | None = None,
    client: SerpApiClient | None = None,
) -> list[tuple[str, str | None, float | None]]:
    """기준일 ±flex_days 범위에서 날짜별 최저가를 조사.

    반환: [(출발일, 귀국일|None, 최저가|None), ...] (출발일 오름차순)

    왕복인 경우:
      - trip_length(여행 일수)를 주면 출발일마다 그만큼 뒤를 귀국일로 잡습니다.
      - 안 주면 base_date~return_date 간격을 여행 일수로 사용합니다.
    """
    client = client or _build_client()
    base = datetime.strptime(base_date, "%Y-%m-%d")

    if return_date and trip_length is None:
        trip_length = (datetime.strptime(return_date, "%Y-%m-%d") - base).days

    results: list[tuple[str, str | None, float | None]] = []
    for delta in range(-flex_days, flex_days + 1):
        out = base + timedelta(days=delta)
        out_str = out.strftime("%Y-%m-%d")
        ret_str = (
            (out + timedelta(days=trip_length)).strftime("%Y-%m-%d")
            if trip_length is not None
            else None
        )
        try:
            offers = search_flights(
                origin=origin,
                destination=destination,
                departure_date=out_str,
                return_date=ret_str,
                currency=currency,
                non_stop=non_stop,
                adults=adults,
                travel_class=travel_class,
                client=client,
            )
            results.append((out_str, ret_str, cheapest_price(offers)))
        except Exception:
            # 특정 날짜 검색이 실패해도 전체는 계속 진행
            results.append((out_str, ret_str, None))

    return results
