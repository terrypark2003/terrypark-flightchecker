"""API 키 없이도 검증 가능한 단위 테스트 (모델 파싱 + 포매팅).

실제 SerpApi(Google Flights) 응답과 동일한 구조의 샘플 JSON으로 검증합니다.
실행: python -m pytest  또는  python tests/test_formatter.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightchecker.formatter import format_results  # noqa: E402
from flightchecker.models import FlightOffer  # noqa: E402

# SerpApi google_flights 응답의 best_flights / other_flights 항목 형태
SAMPLE = {
    "best_flights": [
        {
            "flights": [
                {
                    "departure_airport": {"id": "ICN", "name": "Incheon", "time": "2026-06-06 09:00"},
                    "arrival_airport": {"id": "FUK", "name": "Fukuoka", "time": "2026-06-06 10:25"},
                    "duration": 85,
                    "airline": "Asiana Airlines",
                    "flight_number": "OZ 132",
                }
            ],
            "total_duration": 85,
            "price": 185000,
        }
    ],
    "other_flights": [
        {
            "flights": [
                {
                    "departure_airport": {"id": "ICN", "name": "Incheon", "time": "2026-06-06 07:30"},
                    "arrival_airport": {"id": "NRT", "name": "Tokyo Narita", "time": "2026-06-06 10:00"},
                    "duration": 150,
                    "airline": "Korean Air",
                    "flight_number": "KE 701",
                },
                {
                    "departure_airport": {"id": "NRT", "name": "Tokyo Narita", "time": "2026-06-06 12:00"},
                    "arrival_airport": {"id": "FUK", "name": "Fukuoka", "time": "2026-06-06 13:55"},
                    "duration": 115,
                    "airline": "Korean Air",
                    "flight_number": "KE 787",
                },
            ],
            "total_duration": 385,
            "price": 240000,
        }
    ],
}


def _build_offers():
    raw = SAMPLE["best_flights"] + SAMPLE["other_flights"]
    offers = [FlightOffer.from_api(o, currency="KRW", is_round_trip=True) for o in raw]
    offers.sort(key=lambda o: o.price)
    return offers


def test_parsing():
    offers = _build_offers()
    assert len(offers) == 2
    # 첫 결과(직항)는 구간 1개
    assert len(offers[0].segments) == 1
    assert offers[0].stops == 0
    # 경유편은 구간 2개, 경유 1회
    assert offers[1].stops == 1


def test_sorted_by_price():
    offers = _build_offers()
    assert offers[0].price == 185000.0
    assert offers[1].price == 240000.0


def test_duration_formatting():
    offers = _build_offers()
    assert offers[0].total_duration == "1h25m"
    assert offers[0].segments[0].duration == "1h25m"


def test_format_contains_key_info():
    offers = _build_offers()
    text = format_results(offers, "ICN", "FUK", "2026-06-06", "2026-06-07")
    assert "ICN → FUK" in text
    assert "왕복" in text
    assert "185,000 KRW" in text
    assert "Asiana Airlines" in text
    assert "직항" in text
    assert "경유" in text  # 두 번째 결과


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("\n모든 테스트 통과 ✅\n")
    print("=== 출력 미리보기 ===")
    print(format_results(_build_offers(), "ICN", "FUK", "2026-06-06", "2026-06-07"))
