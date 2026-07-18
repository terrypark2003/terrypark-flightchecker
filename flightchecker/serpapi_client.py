"""SerpApi(Google Flights) 클라이언트.

SerpApi의 google_flights 엔진을 호출해 실제 구글 항공권 데이터를 가져옵니다.
무료 등급은 월 100회 검색을 제공합니다. (https://serpapi.com)
"""

from __future__ import annotations

import requests

_ENDPOINT = "https://serpapi.com/search"


class FlightSearchError(RuntimeError):
    """항공권 검색 API 호출 실패 시 발생하는 예외."""


class SerpApiClient:
    def __init__(self, api_key: str, timeout: int = 30):
        if not api_key:
            raise FlightSearchError(
                "SerpApi 키가 없습니다. .env 파일에 SERPAPI_KEY 를 설정하세요. "
                "(https://serpapi.com 에서 무료 발급)"
            )
        self.api_key = api_key
        self.timeout = timeout

    def flight_offers(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        adults: int = 1,
        currency: str = "KRW",
        non_stop: bool = False,
        travel_class: int | None = None,
        gl: str = "kr",
        hl: str = "ko",
    ) -> dict:
        """google_flights 검색 후 원본 JSON 응답(dict) 반환.

        날짜 형식은 YYYY-MM-DD. return_date를 주면 왕복(type=1), 없으면 편도(type=2).
        """
        params: dict[str, str | int] = {
            "engine": "google_flights",
            "departure_id": origin.upper(),
            "arrival_id": destination.upper(),
            "outbound_date": departure_date,
            "currency": currency,
            "adults": adults,
            "gl": gl,
            "hl": hl,
            "type": 1 if return_date else 2,  # 1=왕복, 2=편도
            "api_key": self.api_key,
        }
        if return_date:
            params["return_date"] = return_date
        if non_stop:
            params["stops"] = 1  # 1 = 직항(non-stop)만
        if travel_class:
            params["travel_class"] = travel_class  # 1=이코노미 2=프리미엄 3=비즈니스 4=일등석

        resp = requests.get(_ENDPOINT, params=params, timeout=self.timeout)
        if resp.status_code != 200:
            raise FlightSearchError(f"항공권 검색 실패 ({resp.status_code}): {resp.text}")

        data = resp.json()
        if "error" in data:
            raise FlightSearchError(f"SerpApi 오류: {data['error']}")
        return data
