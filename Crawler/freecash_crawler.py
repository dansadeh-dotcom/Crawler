from typing import Optional
from typing import Optional
"""
freecash_crawler.py
--------------------
Crawls Freecash teaser offers from the public homepage (freecash.com/en).

Freecash's full logged-in offer wall is still private, but the public landing
page exposes a small set of featured offers in the server-rendered HTML. This
crawler extracts those teaser cards so Freecash appears in the dashboard with
real, non-empty snapshots.
"""

import html
import os
import re
from typing import Optional
from collections.abc import Iterator
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from base_crawler import BaseCrawler, Offer

BASE_URL = "https://freecash.com"
OFFERS_PAGE_URL = f"{BASE_URL}/en"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": BASE_URL,
}

_CARD_RE = re.compile(
    r'<div class="fc-1tovq3n">\s*'
    r'<div class="fc-kwwyi"><img alt="(?P<alt>[^"]+)"[^>]*?src="(?P<src>[^"]+)"[^>]*?></div>\s*'
    r'<div class="fc-164r41r">\s*'
    r'<p[^>]*>(?P<title>.*?)</p>\s*'
    r'<p[^>]*>(?P<description>.*?)</p>\s*'
    r'</div>\s*'
    r'<div class="fc-4ooz0l">.*?'
    r'<p[^>]*>UP TO</p>\s*'
    r'<div class="fc-1byp490">\$(?:<!-- -->)?(?P<dollars>\d+)'
    r'<div class="fc-128nlh6">\.(?:<!-- -->)?(?P<cents>\d{2})</div>',
    re.S,
)


class FreecashCrawler(BaseCrawler):
    PUBLISHER_ID = "freecash"
    PLATFORMS    = ["android", "ios"]

    def __init__(self, config: dict):
        super().__init__(config)
        self._session = self._build_session()

    @classmethod
    def from_env(cls, platform: str = "android") -> "FreecashCrawler":
        """Constructs a FreecashCrawler without requiring credentials."""
        return cls({
            "platform": platform,
            "offers_page_url": os.getenv("FREECASH_OFFERS_PAGE_URL", OFFERS_PAGE_URL),
        })

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(_HEADERS)
        session.mount(
            "https://",
            HTTPAdapter(max_retries=Retry(
                total=3,
                backoff_factor=1.5,
                status_forcelist=[429, 500, 502, 503, 504],
            )),
        )
        return session

    def authenticate(self) -> bool:
        """No authentication is required for the public homepage teaser offers."""
        return True

    def fetch_offers(self) -> Iterator[Offer]:
        """Fetches featured Freecash offers from the public homepage HTML."""
        platform = self.config.get("platform", "android").lower()
        url = self.config.get("offers_page_url", OFFERS_PAGE_URL)

        try:
            response = self._session.get(url, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            self.on_error(exc, {"phase": "fetch", "url": url})
            return

        count = 0
        for index, raw in enumerate(self._extract_offers(response.text), start=1):
            offer = self._norm(raw, platform, index)
            if offer:
                yield offer
                count += 1

        self.logger.info("Freecash: %d teaser offers fetched (platform=%s)", count, platform)

    def _extract_offers(self, html_text: str) -> list[dict]:
        offers = []
        seen_titles = set()
        for match in _CARD_RE.finditer(html_text):
            title = self._clean_text(match.group("title") or match.group("alt"))
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            offers.append({
                "title": title,
                "description": self._clean_text(match.group("description")),
                "payout": f"{match.group('dollars')}.{match.group('cents')}",
                "image": self._resolve_image_url(match.group("src")),
            })
        return offers

    def _resolve_image_url(self, raw_src: str) -> str:
        src = html.unescape(raw_src or "")
        parsed = urlparse(src)
        query_url = parse_qs(parsed.query).get("url", [""])[0]
        if query_url:
            return unquote(query_url)
        return urljoin(BASE_URL, src)

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(value or "").strip())

    def _offer_id(self, title: str, index: int) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return slug or f"freecash-{index}"

    def _norm(self, raw: dict, platform: str, index: int) -> Optional[Offer]:
        """Converts a public Freecash teaser card into a normalised Offer."""
        try:
            payout = float(raw.get("payout", 0))
            title = raw.get("title") or ""
            return Offer(
                publisher   = self.PUBLISHER_ID,
                offer_id    = self._offer_id(title, index),
                title       = title,
                description = raw.get("description") or "",
                payout      = payout,
                currency    = "USD",
                category    = "featured offer",
                platform    = platform,
                icon_url    = raw.get("image") or "",
                preview_url = self.config.get("offers_page_url", OFFERS_PAGE_URL),
                status      = "active",
                raw         = {**raw, "source": "homepage_teaser"},
            )
        except Exception as exc:
            self.on_error(exc, {"phase": "normalize", "raw": raw})
            return None
