"""항공권 검색 결과를 표현하는 데이터 모델.

Amadeus API의 복잡한 JSON 응답을 다루기 쉬운 dataclass로 변환합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


def _parse_dt(value: str) -> datetime:
    """Amadeus의 ISO 8601 시각 문자열을 datetime으로 변환."""
    return datetime.fromisoformat(value)


@dataclass
class FlightSegment:
    """편도 여정 안의 한 구간(한 비행편)."""

    carrier_code: str       # 항공사 코드 (예: OZ, KE)
    flight_number: str      # 편명
    departure_airport: str  # 출발 공항 코드 (예: ICN)
    departure_time: datetime
    arrival_airport: str    # 도착 공항 코드 (예: FUK)
    arrival_time: datetime
    duration: str           # ISO 8601 기간 (예: PT1H25M)

    @classmethod
    def from_api(cls, seg: dict) -> "FlightSegment":
        return cls(
            carrier_code=seg["carrierCode"],
            flight_number=seg["number"],
            departure_airport=seg["departure"]["iataCode"],
            departure_time=_parse_dt(seg["departure"]["at"]),
            arrival_airport=seg["arrival"]["iataCode"],
            arrival_time=_parse_dt(seg["arrival"]["at"]),
            duration=seg.get("duration", ""),
        )


@dataclass
class Itinerary:
    """한 방향(가는 편 또는 오는 편) 전체 여정."""

    duration: str
    segments: list[FlightSegment] = field(default_factory=list)

    @property
    def stops(self) -> int:
        """경유 횟수 (0이면 직항)."""
        return max(len(self.segments) - 1, 0)

    @classmethod
    def from_api(cls, itin: dict) -> "Itinerary":
        return cls(
            duration=itin.get("duration", ""),
            segments=[FlightSegment.from_api(s) for s in itin["segments"]],
        )


@dataclass
class FlightOffer:
    """검색된 항공권 한 건 (왕복이면 가는편+오는편 포함)."""

    price: float
    currency: str
    itineraries: list[Itinerary]
    carrier_names: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_api(cls, offer: dict, carrier_names: dict[str, str] | None = None) -> "FlightOffer":
        return cls(
            price=float(offer["price"]["grandTotal"]),
            currency=offer["price"]["currency"],
            itineraries=[Itinerary.from_api(i) for i in offer["itineraries"]],
            carrier_names=carrier_names or {},
        )

    def carrier_name(self, code: str) -> str:
        """항공사 코드 → 이름(없으면 코드 그대로)."""
        return self.carrier_names.get(code, code)
