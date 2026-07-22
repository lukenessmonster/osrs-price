"""Small client for the OSRS Wiki real-time prices API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://prices.runescape.wiki/api/v1/osrs"


class ApiError(RuntimeError):
    """Raised when the prices API cannot be queried."""


@dataclass(frozen=True)
class Item:
    id: int
    name: str
    members: bool
    limit: int | None = None
    highalch: int | None = None


class PricesClient:
    def __init__(self, contact: str | None = None, timeout: float = 10.0) -> None:
        contact = contact or os.getenv("OSRS_PRICE_CONTACT", "local-user")
        self.user_agent = f"osrs-price/0.1 ({contact})"
        self.timeout = timeout

    def _get(self, route: str, **params: object) -> Any:
        query = urlencode({key: value for key, value in params.items() if value is not None})
        url = f"{BASE_URL}/{route}" + (f"?{query}" if query else "")
        request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            raise ApiError(f"API returned HTTP {error.code}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ApiError(f"Could not reach the OSRS prices API: {error}") from error

    def mapping(self) -> list[Item]:
        return [
            Item(
                id=entry["id"],
                name=entry["name"],
                members=entry["members"],
                limit=entry.get("limit"),
                highalch=entry.get("highalch"),
            )
            for entry in self._get("mapping")
        ]

    def latest(self, item_id: int) -> dict[str, int | None]:
        payload = self._get("latest", id=item_id)
        try:
            return payload["data"][str(item_id)]
        except KeyError as error:
            raise ApiError(f"No price data is available for item ID {item_id}") from error

    def latest_all(self) -> dict[int, dict[str, int | None]]:
        """Return all latest prices in one API request."""
        payload = self._get("latest")
        return {int(item_id): price for item_id, price in payload["data"].items()}

    def timeseries(self, item_id: int, timestep: str) -> list[dict[str, int | None]]:
        return self._get("timeseries", id=item_id, timestep=timestep)["data"]
