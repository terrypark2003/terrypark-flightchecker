"""검색 결과를 사람이 읽기 좋은 텍스트로 변환.

CLI 출력과 텔레그램 메시지 모두에서 재사용합니다 (둘 다 일반 텍스트).
"""

from __future__ import annotations

from datetime import datetime

from .models import FlightOffer


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%m/%d %H:%M")


def format_offer(offer: FlightOffer, index: int | None = None) -> str:
    """항공권 한 건을 여러 줄 텍스트로."""
    header_num = f"{index}. " if index is not None else ""
    price = f"{offer.price:,.0f} {offer.currency}" if offer.price else "가격 정보 없음"
    lines = [f"{header_num}💰 {price}"]

    if not offer.segments:
        return "\n".join(lines)

    first = offer.segments[0]
    last = offer.segments[-1]
    stops = "직항" if offer.stops == 0 else f"{offer.stops}회 경유"
    airlines = " / ".join(sorted({s.airline for s in offer.segments if s.airline}))

    lines.append(
        f"  {first.departure_airport} → {last.arrival_airport}  "
        f"{_fmt_time(first.departure_time)} ~ {_fmt_time(last.arrival_time)}  "
        f"({offer.total_duration}, {stops})"
    )
    if airlines:
        lines.append(f"        ✈ {airlines}")

    # 경유가 있으면 구간별 상세를 덧붙임
    if offer.stops > 0:
        for seg in offer.segments:
            lines.append(
                f"          - {seg.departure_airport}→{seg.arrival_airport} "
                f"{seg.airline} {seg.flight_number} ({seg.duration})"
            )
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
    price_note = (
        f"{cheapest.price:,.0f} {cheapest.currency}" if cheapest.price else "정보 없음"
    )
    round_note = " (왕복 총액)" if return_date else ""
    footer = (
        f"\n\n최저가: {price_note}{round_note} "
        f"· 총 {len(offers)}건 중 상위 {min(limit, len(offers))}건 표시"
    )
    return f"{title}\n\n{body}{footer}"


def format_multi(
    offers: list[FlightOffer],
    legs: list[tuple[str, str, str]],
    limit: int = 5,
) -> str:
    """다구간 검색 결과를 메시지 한 덩어리로.

    가격은 전체 여정 총액, 표시 일정은 첫 구간 기준입니다.
    """
    route = " → ".join([legs[0][0]] + [d for _, d, _ in legs])
    lines = [f"🔎 다구간 {route}"]
    for i, (o, d, date) in enumerate(legs, start=1):
        lines.append(f"  구간{i}. {o}→{d} {date}")
    title = "\n".join(lines)

    if not offers:
        return f"{title}\n\n조건에 맞는 항공권을 찾지 못했습니다."

    body = "\n\n".join(
        format_offer(o, i) for i, o in enumerate(offers[:limit], start=1)
    )
    cheapest = offers[0]
    price_note = (
        f"{cheapest.price:,.0f} {cheapest.currency}" if cheapest.price else "정보 없음"
    )
    footer = (
        f"\n\n최저가: {price_note} (전체 여정 총액, 일정은 첫 구간 기준) "
        f"· 총 {len(offers)}건 중 상위 {min(limit, len(offers))}건 표시"
    )
    return f"{title}\n\n{body}{footer}"


def format_flexible(
    results: list[tuple[str, str | None, float | None]],
    origin: str,
    destination: str,
    currency: str = "KRW",
) -> str:
    """유연한 날짜 검색 결과를 날짜별 최저가 표로."""
    has_return = any(r[1] for r in results)
    trip = "왕복" if has_return else "편도"
    title = f"📅 {origin} → {destination} ({trip}) 날짜별 최저가"

    priced = [(o, r, p) for (o, r, p) in results if p]
    best = min(priced, key=lambda x: x[2]) if priced else None

    lines = [title, ""]
    for out, ret, price in results:
        date_label = out + (f"~{ret}" if ret else "")
        if price is None:
            lines.append(f"  {date_label} : -")
            continue
        mark = "  ⭐" if best and (out, ret, price) == best else ""
        lines.append(f"  {date_label} : {price:,.0f} {currency}{mark}")

    if best:
        b_out, b_ret, b_price = best
        b_label = b_out + (f"~{b_ret}" if b_ret else "")
        lines.append("")
        lines.append(f"가장 싼 날: {b_label} · {b_price:,.0f} {currency}")
    return "\n".join(lines)
