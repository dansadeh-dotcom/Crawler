"""
freecash_crawler.py
--------------------
Crawls the Freecash offer wall (freecash.com).

STATUS: REQUIRES SETUP — see notes below.

HOW FREECASH WORKS
    Freecash is a Next.js app that aggregates offers from many third-party
    offerwall networks (AdGate, AdGem, Lootably, BitLabs, etc.). It does NOT
    expose a public API — offer data is fetched client-side via internal
    XHR requests after login.

HOW TO MAKE THIS CRAWLER WORK
    1. Log in to freecash.com in your browser
    2. Open DevTools (F12) → Network tab → filter by "Fetch/XHR"
    3. Navigate to the offers page and look for the request that returns offer data
    4. Note the endpoint URL, request headers (especially cookies/auth tokens)
    5. Set FREECASH_SESSION_COOKIE in .env with your browser session cookie
    6. Update OFFERS_URL below with the correct endpoint

    Alternatively, since Freecash aggregates from third-party networks,
    consider crawling those networks directly:
      - AdGem:    https://docs.adgem.com  (requires publisher account)
      - Lootably: https://documentation.lootably.com  (requires publisher account)
      - AdGate:   https://docs.prodegeads.com  (requires publisher account)

CREDENTIALS NEEDED (.env):
    FREECASH_EMAIL          your freecash.com email
    FREECASH_PASSWORD       your freecash.com password
    FREECASH_SESSION_COOKIE session cookie from browser (required until login is automated)
"""

import os
from typing import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from base_crawler import BaseCrawler, Offer

BASE_URL = "https://freecash.com"

# TODO: Update this with the correct offers endpoint discovered via browser DevTools
OFFERS_URL = f"{BASE_URL}/api/offers"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": BASE_URL,
}


class FreecashCrawler(BaseCrawler):
    PUBLISHER_ID = "freecash"
    PLATFORMS    = ["android", "ios"]

    def __init__(self, config: dict):
        super().__init__(config)
        self._authenticated = False
        self._session = self._build_session()

    @classmethod
    def from_env(cls, platform: str = "android") -> "FreecashCrawler":
        """Constructs a FreecashCrawler from FREECASH_* environment variables."""
        raise NotImplementedError(
            "Freecash crawler not yet implemented — login automation is pending. "
            "See freecash_crawler.py for notes."
        )

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
        return s

    def authenticate(self) -> bool:
        """
        Authenticates with Freecash.

        Uses a pre-set session cookie if available. Direct login automation
        is not yet implemented — Freecash uses a Next.js auth flow that
        requires further reverse-engineering.
        """
        cookie_str = self.config.get("session_cookie", "")
        if cookie_str:
            self._session.headers["Cookie"] = cookie_str
            self._authenticated = True
            self.logger.info("Freecash: using session cookie from .env")
            return True

        self.logger.warning(
            "Freecash: automated login not yet implemented. "
            "Set FREECASH_SESSION_COOKIE in .env. See freecash_crawler.py for instructions."
        )
        return False

    def fetch_offers(self) -> Iterator[Offer]:
        """
        Fetches mobile game offers from Freecash.

        NOTE: The correct API endpoint needs to be discovered via browser DevTools.
        Update OFFERS_URL at the top of this file once found.
        """
        if not self._authenticated and not self.authenticate():
            return

        platform = self.config.get("platform", "android").lower()

        try:
            resp = self._session.get(
                OFFERS_URL,
                params={"platform": platform, "category": "games"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.on_error(exc, {"phase": "fetch"})
            self.logger.error(
                "Freecash fetch failed. The API endpoint may need updating — "
                "check OFFERS_URL in freecash_crawler.py. Error: %s", exc
            )
            return

        offers_list = (
            data if isinstance(data, list)
            else data.get("offers") or data.get("data") or data.get("results") or []
        )

        count = 0
        for raw in offers_list:
            offer = self._norm(raw, platform)
            if offer:
                yield offer
                count += 1

        self.logger.info("Freecash: %d offers fetched (platform=%s)", count, platform)

    def _norm(self, raw: dict, platform: str) -> Offer | None:
        """Converts a raw Freecash API item into a normalised Offer."""
        try:
            raw_platform = (
                raw.get("platform") or raw.get("device") or platform
            ).lower()

            payout_raw = raw.get("amount") or raw.get("payout") or raw.get("reward") or 0
            try:
                payout = float(str(payout_raw).replace("$", "").replace(",", "").strip())
            except (ValueError, TypeError):
                payout = 0.0

            return Offer(
                publisher   = self.PUBLISHER_ID,
                offer_id    = str(raw.get("id") or raw.get("offer_id") or ""),
                title       = raw.get("title") or raw.get("name") or "",
                description = raw.get("description") or "",
                payout      = payout,
                currency    = "USD",
                category    = raw.get("category") or "game",
                platform    = raw_platform,
                icon_url    = raw.get("icon") or raw.get("image") or "",
                preview_url = raw.get("url") or raw.get("link") or "",
                status      = "active",
                raw         = raw,
            )
        except Exception as exc:
            self.on_error(exc, {"phase": "normalize", "raw": raw})
            return None
