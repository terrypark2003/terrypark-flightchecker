"""항공권 검색 결과를 표현하는 데이터 모델.

SerpApi(Google Flights) 응답 JSON을 다루기 쉬운 dataclass로 변환합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def _parse_dt(value: str) -> datetime:
    """SerpApi 시각 문자열("2026-06-06 09:00")을 datetime으로 변환."""
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def _fmt_minutes(minutes: int) -> str:
    """분 단위 정수를 "1h25m" 형태로 변환."""
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}h{m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


@dataclass
class FlightSegment:
    """한 여정 안의 한 구간(한 비행편)."""

    airline: str            # 항공사 이름 (예: ASIANA)
    flight_number: str      # 편명
    departure_airport: str  # 출발 공항 코드 (예: ICN)
    departure_time: datetime
    arrival_airport: str    # 도착 공항 코드 (예: FUK)
    arrival_time: datetime
    duration: str           # 사람이 읽는 기간 (예: 1h25m)

    @classmethod
    def from_api(cls, seg: dict) -> "FlightSegment":
        return cls(
            airline=seg.get("airline", ""),
            flight_number=seg.get("flight_number", ""),
            departure_airport=seg["departure_airport"]["id"],
            departure_time=_parse_dt(seg["departure_airport"]["time"]),
            arrival_airport=seg["arrival_airport"]["id"],
            arrival_time=_parse_dt(seg["arrival_airport"]["time"]),
            duration=_fmt_minutes(seg.get("duration", 0)),
        )


@dataclass
class FlightOffer:
    """검색된 항공권 한 건.

    SerpApi의 왕복 검색은 1차 응답에 '가는편' 여정과 '왕복 총액'을 줍니다.
    (오는편 상세는 departure_token으로 2차 조회가 필요하므로 여기서는
    가는편 여정 + 총 가격을 기준으로 보여줍니다.)
    """

    price: float
    currency: str
    segments: list[FlightSegment]
    total_duration: str           # 가는편 총 소요 (예: 1h25m)
    is_round_trip: bool = False
    duration_minutes: int = 0     # 가는편 총 소요 (분) - 경유 제외 정책 판단용

    @property
    def stops(self) -> int:
        """경유 횟수 (0이면 직항)."""
        return max(len(self.segments) - 1, 0)

    @classmethod
    def from_api(cls, offer: dict, currency: str, is_round_trip: bool = False) -> "FlightOffer":
        return cls(
            price=float(offer.get("price", 0)),
            currency=currency,
            segments=[FlightSegment.from_api(s) for s in offer.get("flights", [])],
            total_duration=_fmt_minutes(offer.get("total_duration", 0)),
            is_round_trip=is_round_trip,
            duration_minutes=int(offer.get("total_duration", 0)),
        )
