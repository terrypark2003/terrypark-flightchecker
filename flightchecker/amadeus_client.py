"""Amadeus Self-Service API 클라이언트.

OAuth2 토큰 발급 및 항공권 검색(Flight Offers Search) 호출을 담당합니다.
토큰은 만료 전까지 메모리에 캐시해서 재사용합니다.
"""

from __future__ import annotations

import time

import requests

_HOSTS = {
    "test": "https://test.api.amadeus.com",
    "production": "https://api.amadeus.com",
}


class AmadeusError(RuntimeError):
    """Amadeus API 호출 실패 시 발생하는 예외."""


class AmadeusClient:
    def __init__(self, client_id: str, client_secret: str, env: str = "test", timeout: int = 20):
        if not client_id or not client_secret:
            raise AmadeusError(
                "Amadeus 자격증명이 없습니다. .env 파일에 AMADEUS_CLIENT_ID / "
                "AMADEUS_CLIENT_SECRET 을 설정하세요."
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = _HOSTS.get(env, _HOSTS["test"])
        self.timeout = timeout
        self._token: str | None = None
        self._token_expiry: float = 0.0

    # ---- 인증 -------------------------------------------------------------
    def _get_token(self) -> str:
        """유효한 access token 반환 (만료 60초 전이면 새로 발급)."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        resp = requests.post(
            f"{self.base_url}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise AmadeusError(f"토큰 발급 실패 ({resp.status_code}): {resp.text}")

        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 1799)
        return self._token

    # ---- 항공권 검색 ------------------------------------------------------
    def flight_offers(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        adults: int = 1,
        currency: str = "KRW",
        non_stop: bool = False,
        max_results: int = 10,
    ) -> dict:
        """Flight Offers Search 호출 후 원본 JSON 응답(dict) 반환.

        날짜 형식은 YYYY-MM-DD. return_date를 주면 왕복으로 검색합니다.
        """
        params: dict[str, str | int | bool] = {
            "originLocationCode": origin.upper(),
            "destinationLocationCode": destination.upper(),
            "departureDate": departure_date,
            "adults": adults,
            "currencyCode": currency,
            "max": max_results,
        }
        if return_date:
            params["returnDate"] = return_date
        if non_stop:
            params["nonStop"] = "true"

        resp = requests.get(
            f"{self.base_url}/v2/shopping/flight-offers",
            params=params,
            headers={"Authorization": f"Bearer {self._get_token()}"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise AmadeusError(f"항공권 검색 실패 ({resp.status_code}): {resp.text}")
        return resp.json()
