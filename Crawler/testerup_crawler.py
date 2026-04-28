"""
testerup_crawler.py
--------------------
Handles all communication with the TesterUP API.

What it does:
  1. Authenticates with your TesterUP account (email + password via their web login flow)
  2. Fetches the full offer wall using TesterUP's private GraphQL API
  3. Returns each offer (and story) as a normalised Offer object

This file is NOT meant to be run directly — it is imported and used by run.py.
"""

import logging
from typing import Iterator
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from base_crawler import BaseCrawler, Offer

# ── API endpoints ──────────────────────────────────────────────────────────────
BASE_WEB_URL = "https://www.testerup.com"
AUTH_URL     = "https://www.testerup.com/api/auth/session"
GRAPHQL_URL  = "https://api.v2.testerup.com/graphql/"

# ── GraphQL query ──────────────────────────────────────────────────────────────
# This is the main query that fetches the offer wall.
# It returns both "offers" (games/apps with payout) and "stories" (promotional content).
# targetingId is included so the dashboard can later fetch per-event payout breakdowns.
USER_CONTENT_QUERY = """
query UserContent($contentData: UserContentInput!) {
  userContent(contentData: $contentData) {
    success
    stories { id name thumbnailImagePath storyContentPath sortOrder payout { amount currencyCode } }
    offers { id title imageUrl category { name } targetDeviceType targetingId payout { amount currencyCode } trackingUrl isNew isPremium sortOrder }

  }
}
"""

# Default variables for the query.
# storiesDeviceType is overridden at runtime to "android" or "ios" depending on the run.
USER_CONTENT_VARIABLES = {"contentData": {"advertisingId": None, "appVersion": None, "deviceType": "desktop", "storiesDeviceType": "android", "deviceId": None, "offers": True, "stories": True, "surveys": False}}


class TesterUpCrawler(BaseCrawler):
    PUBLISHER_ID = "testerup"
    PLATFORMS    = ["android", "ios", "desktop"]

    @classmethod
    def from_env(cls, platform: str = "android") -> "TesterUpCrawler":
        """Constructs a TesterUpCrawler from TESTERUP_* environment variables."""
        import os
        email    = os.getenv("TESTERUP_EMAIL")
        password = os.getenv("TESTERUP_PASSWORD")
        if not email or not password:
            raise EnvironmentError(
                "TESTERUP_EMAIL and TESTERUP_PASSWORD must be set in .env"
            )
        return cls({
            "email":      email,
            "password":   password,
            "country":    os.getenv("TESTERUP_COUNTRY", "US"),
            "platform":   platform,
            "page_size":  50,
            "rate_limit": 1.0,
        })

    def __init__(self, config):
        super().__init__(config)
        self._token = None
        self._session = self._build_session()

    def _build_session(self):
        """
        Creates an HTTP session with automatic retries on server errors.
        Retries up to 3 times with increasing wait times between attempts.
        """
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        session.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])))
        return session

    def authenticate(self):
        """
        Logs in to TesterUP using a 3-step web authentication flow:
          Step 1 — Load the homepage to receive the CSRF cookie
          Step 2 — Submit email + password along with the CSRF token
          Step 3 — Fetch the session to extract the Bearer access token

        The access token is stored and attached to all future API requests.
        Returns True on success, False on failure.
        """
        # Step 1: Load homepage — TesterUP sets the CSRF token as a cookie
        # (the old /api/auth/csrf endpoint now returns 403)
        try:
            self._session.get(f"{BASE_WEB_URL}/", timeout=15)
            raw_cookie = self._session.cookies.get("__Host-next-auth.csrf-token", "")
            if not raw_cookie:
                self.logger.error("CSRF cookie not set after loading homepage"); return False
            from urllib.parse import unquote
            csrf = unquote(raw_cookie).split("|")[0]
            self.logger.info("CSRF: %s...", csrf[:10])
        except Exception as e:
            self.on_error(e, {"phase": "csrf"}); return False

        # Step 2: Submit login credentials
        try:
            resp = self._session.post(
                f"{BASE_WEB_URL}/api/auth/callback/credentials",
                data=urlencode({"email": self.config["email"], "password": self.config["password"], "csrfToken": csrf, "redirect": "false", "newUser": "false", "callbackUrl": "https://www.testerup.com/dashboard?provider=email&method=login", "json": "true"}),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15, allow_redirects=True,
            )
            self.logger.info("Login status: %s", resp.status_code)
            if resp.status_code not in (200, 302):
                self.logger.error("Login failed: %s", resp.text[:200]); return False
        except Exception as e:
            self.on_error(e, {"phase": "login"}); return False

        # Step 3: Extract Bearer token from session
        try:
            data = self._session.get(AUTH_URL, timeout=15).json()
            self._token = data.get("user", {}).get("accessToken") or data.get("accessToken")
            if not self._token:
                self.logger.error("No token: %s", data); return False
            self._session.headers["Authorization"] = f"Bearer {self._token}"
            self.logger.info("Auth OK: %s", data.get("user", {}).get("email"))
            return True
        except Exception as e:
            self.on_error(e, {"phase": "session"}); return False

    def fetch_offers(self):
        """
        Calls the TesterUP GraphQL API to fetch all visible offers and stories
        for the configured platform (android or ios).

        Yields one Offer object per item. Each offer includes:
          - title, payout, category, platform, icon URL, tracking URL
          - targetingId (used later to fetch per-event breakdowns)
          - the full raw API response (stored as-is for future use)
        """
        # Authenticate first if we don't have a token yet
        if not self._token and not self.authenticate():
            return

        # Set the platform (android or ios) for this crawl run
        platform = self.config.get("platform", "android").lower()
        variables = {**USER_CONTENT_VARIABLES, "contentData": {**USER_CONTENT_VARIABLES["contentData"], "storiesDeviceType": platform}}

        # Call the GraphQL API
        try:
            resp = self._session.post(GRAPHQL_URL, json={"query": USER_CONTENT_QUERY, "variables": variables, "operationName": "UserContent"}, headers={"Content-Type": "application/json", "Accept": "application/json"}, timeout=30)
            resp.raise_for_status()
            uc = resp.json().get("data", {}).get("userContent", {})
        except Exception as e:
            self.on_error(e, {"phase": "fetch"}); return

        if not uc.get("success"):
            self.logger.error("Error: %s", uc.get("error")); return

        # Yield normalised offers, then stories
        for raw in uc.get("offers", []):
            o = self._norm(raw, "offer")
            if o: yield o
        for raw in uc.get("stories", []):
            o = self._norm(raw, "story")
            if o: yield o
        self.logger.info("Done: %d offers, %d stories", len(uc.get("offers",[])), len(uc.get("stories",[])))

    def _norm(self, raw, kind):
        """
        Converts a raw API response item into a standardised Offer object.
        Handles both "offer" (game/app) and "story" (promotional content) types.
        Returns None and logs an error if anything goes wrong.
        """
        try:
            return Offer(
                publisher=self.PUBLISHER_ID,
                offer_id=f"{'story_' if kind=='story' else ''}{raw.get('id','')}",
                title=raw.get("name" if kind=="story" else "title", ""),
                description="",
                payout=float((raw.get("payout") or raw.get("reward") or {}).get("amount", 0)),
                currency=(raw.get("payout") or raw.get("reward") or {}).get("currencyCode", "USD"),
                category="story" if kind=="story" else (raw.get("category") or {}).get("name",""),
                platform=raw.get("targetDeviceType","android"),
                icon_url=raw.get("thumbnailImagePath" if kind=="story" else "imageUrl",""),
                preview_url=raw.get("storyContentPath" if kind=="story" else "trackingUrl",""),
                status="active", raw=raw,
            )
        except Exception as e:
            self.on_error(e, {"phase": "normalize", "raw": raw}); return None
