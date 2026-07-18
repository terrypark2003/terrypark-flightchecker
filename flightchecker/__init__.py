"""terrypark-flightchecker: SerpApi(Google Flights) 기반 항공권 검색 코어 패키지.

CLI(cli.py)와 텔레그램 봇(bot.py)이 모두 이 패키지를 import해서 사용합니다.
"""

from .models import FlightOffer, FlightSegment
from .search import search_flights, search_flexible_dates, cheapest_price, drop_layovers
from .serpapi_client import SerpApiClient, FlightSearchError
from .airports import resolve_airport
from .watchstore import Watch, WatchStore
from .pricehistory import PriceHistory, route_key
from .options import parse_search_options, describe_options
from .links import google_flights_url, skyscanner_url

__all__ = [
    "FlightOffer",
    "FlightSegment",
    "search_flights",
    "search_flexible_dates",
    "cheapest_price",
    "drop_layovers",
    "SerpApiClient",
    "FlightSearchError",
    "resolve_airport",
    "Watch",
    "WatchStore",
    "PriceHistory",
    "route_key",
    "parse_search_options",
    "describe_options",
    "google_flights_url",
    "skyscanner_url",
]
