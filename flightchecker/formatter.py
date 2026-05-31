"""검색 결과를 사람이 읽기 좋은 텍스트로 변환.

CLI 출력과 텔레그램 메시지 모두에서 재사용합니다 (둘 다 일반 텍스트).
"""

from __future__ import annotations

from datetime import datetime

from .models import FlightOffer, Itinerary


def _fmt_duration(iso: str) -> str:
    """PT1H25M -> 1h25m 형태로 간단 변환."""
    out = iso.replace("PT", "").replace("H", "h").replace("M", "m")
    return out.lower()


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%m/%d %H:%M")


def _format_itinerary(itin: Itinerary, offer: FlightOffer, label: str) -> str:
    first = itin.segments[0]
    last = itin.segments[-1]
    stops = "직항" if itin.stops == 0 else f"{itin.stops}회 경유"
    carriers = " / ".join(
        sorted({offer.carrier_name(s.carrier_code) for s in itin.segments})
    )
    return (
        f"  [{label}] {first.departure_airport} → {last.arrival_airport}  "
        f"{_fmt_time(first.departure_time)} ~ {_fmt_time(last.arrival_time)}  "
        f"({_fmt_duration(itin.duration)}, {stops})\n"
        f"        ✈ {carriers}"
    )


def format_offer(offer: FlightOffer, index: int | None = None) -> str:
    """항공권 한 건을 여러 줄 텍스트로."""
    header_num = f"{index}. " if index is not None else ""
    price = f"{offer.price:,.0f} {offer.currency}"
    lines = [f"{header_num}💰 {price}"]

    labels = ["가는편", "오는편"]
    for i, itin in enumerate(offer.itineraries):
        label = labels[i] if i < len(labels) else f"여정{i + 1}"
        lines.append(_format_itinerary(itin, offer, label))
    return "\n".join(lines)


def format_results(
    offers: list[FlightOffer],
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    limit: int = 5,
) -> str:
    """검색 결과 전체를 메시지 한 덩어리로 (상위 limit개)."""
    trip = "왕복" if return_date else "편도"
    date_part = departure_date + (f" ~ {return_date}" if return_date else "")
    title = f"🔎 {origin} → {destination} ({trip}) {date_part}"

    if not offers:
        return f"{title}\n\n조건에 맞는 항공권을 찾지 못했습니다."

    body = "\n\n".join(
        format_offer(o, i) for i, o in enumerate(offers[:limit], start=1)
    )
    cheapest = offers[0]
    footer = (
        f"\n\n최저가: {cheapest.price:,.0f} {cheapest.currency} "
        f"(총 {len(offers)}건 중 상위 {min(limit, len(offers))}건 표시)"
    )
    return f"{title}\n\n{body}{footer}"
