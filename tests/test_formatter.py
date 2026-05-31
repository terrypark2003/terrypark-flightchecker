"""API 키 없이도 검증 가능한 단위 테스트 (모델 파싱 + 포매팅).

실제 Amadeus 응답과 동일한 구조의 샘플 JSON으로 검증합니다.
실행: python -m pytest  또는  python tests/test_formatter.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightchecker.formatter import format_results  # noqa: E402
from flightchecker.models import FlightOffer  # noqa: E402

SAMPLE = {
    "data": [
        {
            "price": {"grandTotal": "185000.00", "currency": "KRW"},
            "itineraries": [
                {
                    "duration": "PT1H25M",
                    "segments": [
                        {
                            "carrierCode": "OZ",
                            "number": "132",
                            "departure": {"iataCode": "ICN", "at": "2026-06-06T09:00:00"},
                            "arrival": {"iataCode": "FUK", "at": "2026-06-06T10:25:00"},
                            "duration": "PT1H25M",
                        }
                    ],
                },
                {
                    "duration": "PT1H30M",
                    "segments": [
                        {
                            "carrierCode": "OZ",
                            "number": "133",
                            "departure": {"iataCode": "FUK", "at": "2026-06-07T18:00:00"},
                            "arrival": {"iataCode": "ICN", "at": "2026-06-07T19:30:00"},
                            "duration": "PT1H30M",
                        }
                    ],
                },
            ],
        },
        {
            "price": {"grandTotal": "240000.00", "currency": "KRW"},
            "itineraries": [
                {
                    "duration": "PT1H20M",
                    "segments": [
                        {
                            "carrierCode": "KE",
                            "number": "787",
                            "departure": {"iataCode": "ICN", "at": "2026-06-06T07:30:00"},
                            "arrival": {"iataCode": "FUK", "at": "2026-06-06T08:50:00"},
                            "duration": "PT1H20M",
                        }
                    ],
                },
                {
                    "duration": "PT1H25M",
                    "segments": [
                        {
                            "carrierCode": "KE",
                            "number": "788",
                            "departure": {"iataCode": "FUK", "at": "2026-06-07T20:00:00"},
                            "arrival": {"iataCode": "ICN", "at": "2026-06-07T21:25:00"},
                            "duration": "PT1H25M",
                        }
                    ],
                },
            ],
        },
    ],
    "dictionaries": {"carriers": {"OZ": "ASIANA AIRLINES", "KE": "KOREAN AIR"}},
}


def _build_offers():
    carriers = SAMPLE["dictionaries"]["carriers"]
    offers = [FlightOffer.from_api(o, carriers) for o in SAMPLE["data"]]
    offers.sort(key=lambda o: o.price)
    return offers


def test_parsing():
    offers = _build_offers()
    assert len(offers) == 2
    # 왕복이므로 여정 2개
    assert len(offers[0].itineraries) == 2
    # 직항 확인
    assert offers[0].itineraries[0].stops == 0


def test_sorted_by_price():
    offers = _build_offers()
    assert offers[0].price == 185000.0
    assert offers[1].price == 240000.0


def test_carrier_name_lookup():
    offers = _build_offers()
    assert offers[0].carrier_name("OZ") == "ASIANA AIRLINES"


def test_format_contains_key_info():
    offers = _build_offers()
    text = format_results(offers, "ICN", "FUK", "2026-06-06", "2026-06-07")
    assert "ICN → FUK" in text
    assert "왕복" in text
    assert "185,000 KRW" in text
    assert "ASIANA AIRLINES" in text
    assert "가는편" in text and "오는편" in text


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("\n모든 테스트 통과 ✅\n")
    print("=== 출력 미리보기 ===")
    print(format_results(_build_offers(), "ICN", "FUK", "2026-06-06", "2026-06-07"))
