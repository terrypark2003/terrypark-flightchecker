"""terrypark-flightchecker: SerpApi(Google Flights) 기반 항공권 검색 코어 패키지.

CLI(cli.py)와 텔레그램 봇(bot.py)이 모두 이 패키지를 import해서 사용합니다.
"""

from .models import FlightOffer, FlightSegment
from .search import search_flights
from .serpapi_client import SerpApiClient, FlightSearchError

__all__ = [
    "FlightOffer",
    "FlightSegment",
    "search_flights",
    "SerpApiClient",
    "FlightSearchError",
]
