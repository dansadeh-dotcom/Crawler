"""
kashkick_crawler.py
--------------------
Crawls the Kashkick offer wall (app.kashkick.com).

HOW IT WORKS
    Kashkick exposes a public REST API at app.kashkick.com/wp-api/offers that
    requires NO authentication. Offers are Android-only (platform=2 in the API).

    Amount field: raw value in cents (e.g. 850 → $8.50).
    Platform field: 2 = Android (only value observed in the API).

NO CREDENTIALS NEEDED — this crawler works out of the box.
"""

import re
from collections.abc import Iterator
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from base_crawler import BaseCrawler, Offer, configure_session_proxy

BASE_URL   = "https://app.kashkick.com"
OFFERS_URL = f"{BASE_URL}/wp-api/offers"

# Kashkick platform codes observed in the API
_PLATFORM_MAP = {
    1: "ios",
    2: "android",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": BASE_URL,
}


class KashkickCrawler(BaseCrawler):
    PUBLISHER_ID = "kashkick"
    PLATFORMS    = ["android"]   # API only returns Android offers currently

    def __init__(self, config: dict):
        super().__init__(config)
        self._session = self._build_session()

    @classmethod
    def from_env(cls, platform: str = "android") -> "KashkickCrawler":
        """No credentials needed — Kashkick's offer API is public."""
        return cls({"platform": platform})

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(_HEADERS)
        s.mount(
            "https://",
            HTTPAdapter(max_retries=Retry(
                total=3, backoff_factor=1.5,
                status_forcelist=[429, 500, 502, 503, 504],
            )),
        )
        configure_session_proxy(s, self.PUBLISHER_ID)
        return s

    def authenticate(self) -> bool:
        """No authentication required for Kashkick's public offer API."""
        return True

    def fetch_offers(self) -> Iterator[Offer]:
        """Fetches all game offers from Kashkick's public REST API."""
        try:
            resp = self._session.get(
                OFFERS_URL,
                params={"order-by": "amount", "order": "desc"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.on_error(exc, {"phase": "fetch"})
            return

        offers_list = data if isinstance(data, list) else data.get("offers") or []

        count = 0
        for raw in offers_list:
            offer = self._norm(raw)
            if offer:
                yield offer
                count += 1

        self.logger.info("Kashkick: %d offers fetched", count)

    def _norm(self, raw: dict) -> Optional[Offer]:
        """Converts a raw Kashkick API item into a normalised Offer."""
        try:
            # Platform: integer code → string name
            platform = _PLATFORM_MAP.get(raw.get("platform"), "android")

            # Amount: raw value in cents → USD
            try:
                payout = round(float(raw.get("amount", 0)) / 100, 2)
            except (ValueError, TypeError):
                payout = 0.0

            # Category: use the primary category from the categories array
            categories = raw.get("categories") or []
            primary = next(
                (c["name"] for c in categories if c.get("primary")),
                (categories[0]["name"] if categories else "Game"),
            )

            # Strip HTML tags from description
            desc_html = raw.get("description") or raw.get("cardText") or ""
            description = re.sub(r"<[^>]+>", "", desc_html).strip()

            return Offer(
                publisher   = self.PUBLISHER_ID,
                offer_id    = str(raw.get("id") or raw.get("title", "").lower().replace(" ", "-")),
                title       = raw.get("title") or "",
                description = description,
                payout      = payout,
                currency    = "USD",
                category    = primary,
                platform    = platform,
                icon_url    = raw.get("image") or raw.get("largeImage") or "",
                preview_url = "",
                status      = "active",
                raw         = raw,
            )
        except Exception as exc:
            self.on_error(exc, {"phase": "normalize", "raw": raw})
            return None
