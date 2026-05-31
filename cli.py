#!/usr/bin/env python3
"""커맨드라인 항공권 검색기.

사용 예 (인천-후쿠오카 왕복, 6/6 출발 6/7 귀국):
    python cli.py ICN FUK 2026-06-06 --return 2026-06-07
    python cli.py ICN FUK 2026-06-06 -r 2026-06-07 --non-stop --adults 2
"""

from __future__ import annotations

import argparse
import sys

from flightchecker import AmadeusError, search_flights
from flightchecker.formatter import format_results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Amadeus 기반 항공권 검색기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="예: python cli.py ICN FUK 2026-06-06 -r 2026-06-07",
    )
    parser.add_argument("origin", help="출발지 공항/도시 코드 (예: ICN)")
    parser.add_argument("destination", help="도착지 공항/도시 코드 (예: FUK)")
    parser.add_argument("departure_date", help="출발일 YYYY-MM-DD")
    parser.add_argument("-r", "--return", dest="return_date", help="귀국일 YYYY-MM-DD (왕복)")
    parser.add_argument("--adults", type=int, default=1, help="성인 인원 (기본 1)")
    parser.add_argument("--currency", default="KRW", help="통화 (기본 KRW)")
    parser.add_argument("--non-stop", action="store_true", help="직항만 검색")
    parser.add_argument("--max", dest="max_results", type=int, default=10, help="가져올 후보 수")
    parser.add_argument("--limit", type=int, default=5, help="화면에 표시할 건수")
    args = parser.parse_args(argv)

    try:
        offers = search_flights(
            origin=args.origin,
            destination=args.destination,
            departure_date=args.departure_date,
            return_date=args.return_date,
            adults=args.adults,
            currency=args.currency,
            non_stop=args.non_stop,
            max_results=args.max_results,
        )
    except AmadeusError as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        return 1

    print(
        format_results(
            offers,
            origin=args.origin.upper(),
            destination=args.destination.upper(),
            departure_date=args.departure_date,
            return_date=args.return_date,
            limit=args.limit,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
