from typing import Optional
from typing import Optional
"""
swagbucks_crawler.py
---------------------
Crawls the Swagbucks offer wall (swagbucks.com).

STATUS: REQUIRES SETUP — see notes below.

HOW SWAGBUCKS WORKS
    Swagbucks is owned by Prodege, which also owns AdGate Media. Their offer
    walls are powered by third-party offerwall networks rendered in iframes.
    Swagbucks does not expose a public API for fetching offers programmatically.

HOW TO MAKE THIS CRAWLER WORK

    OPTION A — Browser session scraping (reverse-engineered):
      1. Log in to swagbucks.com in your browser
      2. Open DevTools (F12) → Network tab → filter by "Fetch/XHR"
      3. Navigate to Discover → Apps & Games offers
      4. Find the XHR request(s) that load the offer list
      5. Note the endpoint, headers, and any auth tokens
      6. Set SWAGBUCKS_SESSION_COOKIE in .env and update OFFERS_URL below

    OPTION B — AdGate Media publisher API (recommended):
      Since Prodege owns both Swagbucks and AdGate, the AdGate publisher API
      gives access to the same offer catalog:
        Docs: https://docs.prodegeads.com/publisher-apis/offers-api
      1. Register as a publisher at adgatemedia.com
      2. Get your affiliate_id and api_key
      3. Set ADGATE_AFFILIATE_ID and ADGATE_API_KEY in .env
      4. Update this crawler to call the AdGate API

CREDENTIALS NEEDED (.env):
    SWAGBUCKS_EMAIL          your swagbucks.com email
    SWAGBUCKS_PASSWORD       your swagbucks.com password
    SWAGBUCKS_SESSION_COOKIE session cookie from browser (Option A)
    # -- OR --
    ADGATE_AFFILIATE_ID      AdGate publisher affiliate ID (Option B)
    ADGATE_API_KEY           AdGate publisher API key (Option B)
"""

import os
from collections.abc import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from base_crawler import BaseCrawler, Offer

BASE_URL = "https://www.swagbucks.com"

# TODO: Update with the correct endpoint (Option A) or switch to AdGate API (Option B)
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


class SwagbucksCrawler(BaseCrawler):
    PUBLISHER_ID = "swagbucks"
    PLATFORMS    = ["android", "ios"]

    def __init__(self, config: dict):
        super().__init__(config)
        self._authenticated = False
        self._session = self._build_session()

    @classmethod
    def from_env(cls, platform: str = "android") -> "SwagbucksCrawler":
        """Constructs a SwagbucksCrawler from SWAGBUCKS_* environment variables."""
        session_cookie = os.getenv("SWAGBUCKS_SESSION_COOKIE", "")
        email          = os.getenv("SWAGBUCKS_EMAIL", "")
        password       = os.getenv("SWAGBUCKS_PASSWORD", "")

        if not session_cookie and not (email and password):
            raise OSError(
                "Swagbucks requires either SWAGBUCKS_SESSION_COOKIE or "
                "SWAGBUCKS_EMAIL + SWAGBUCKS_PASSWORD in .env. "
                "See swagbucks_crawler.py for setup instructions."
            )
        return cls({
            "email":          email,
            "password":       password,
            "session_cookie": session_cookie,
            "platform":       platform,
        })

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
        Authenticates with Swagbucks using a pre-set session cookie.

        Direct login automation is not yet implemented. See swagbucks_crawler.py
        for the two options available (browser session scraping or AdGate API).
        """
        cookie_str = self.config.get("session_cookie", "")
        if cookie_str:
            self._session.headers["Cookie"] = cookie_str
            self._authenticated = True
            self.logger.info("Swagbucks: using session cookie from .env")
            return True

        self.logger.warning(
            "Swagbucks: automated login not yet implemented. "
            "Set SWAGBUCKS_SESSION_COOKIE in .env, or implement the AdGate API option. "
            "See swagbucks_crawler.py for instructions."
        )
        return False

    def fetch_offers(self) -> Iterator[Offer]:
        """
        Fetches mobile game offers from Swagbucks.

        NOTE: The correct API endpoint needs to be discovered. See OPTION A/B
        in swagbucks_crawler.py for how to set this up.
        """
        if not self._authenticated and not self.authenticate():
            return

        platform = self.config.get("platform", "android").lower()

        try:
            resp = self._session.get(
                OFFERS_URL,
                params={"platform": platform, "type": "mobile"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.on_error(exc, {"phase": "fetch"})
            self.logger.error(
                "Swagbucks fetch failed. The API endpoint needs to be configured — "
                "see OFFERS_URL in swagbucks_crawler.py. Error: %s", exc
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

        self.logger.info("Swagbucks: %d offers fetched (platform=%s)", count, platform)

    def _norm(self, raw: dict, platform: str) -> Optional[Offer]:
        """Converts a raw Swagbucks API item into a normalised Offer."""
        try:
            raw_platform = (
                raw.get("platform") or raw.get("device") or platform
            ).lower()

            payout_raw = raw.get("amount") or raw.get("payout") or raw.get("value") or 0
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
