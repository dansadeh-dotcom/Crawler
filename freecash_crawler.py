"""
freecash_crawler.py
--------------------
Crawls the Freecash offer wall via the private GraphQL API (authenticated).

HOW IT WORKS — AUTHENTICATED MODE (default)
    Freecash exposes a private GraphQL API at freecash.com/fc-api/graphql.
    Authentication requires an `fc_access_token` JWT cookie from the browser.

    To get a fresh token:
      1. Log in at freecash.com in Chrome/Firefox
      2. DevTools → Application → Cookies → freecash.com → fc_access_token
      3. Set FREECASH_ACCESS_TOKEN in .env
      The token is valid for 90 days.

HOW IT WORKS — FALLBACK MODE (no token)
    If FREECASH_ACCESS_TOKEN is missing, falls back to scraping the public
    homepage for a small set of teaser offer cards (3–5 offers, no full wall).

PLATFORM DETECTION
    Freecash offers don't have an explicit platform field. Platform is inferred
    from the offer name/slug:
      - "android" in name/slug → android
      - "ios" / "iphone" in name/slug → ios
      - no indicator              → all platforms (yielded for every run)
    Coin conversion: 1000 Freecash coins = $1 USD (standard user rate).

CREDENTIALS NEEDED (.env):
    FREECASH_ACCESS_TOKEN    fc_access_token JWT cookie from browser (90-day TTL)
"""

import html
import os
import re
from collections.abc import Iterator
from typing import Optional
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from base_crawler import BaseCrawler, Offer, configure_session_proxy

BASE_URL       = "https://freecash.com"
OFFERS_PAGE_URL = f"{BASE_URL}/en"
FC_GQL_URL     = f"{BASE_URL}/fc-api/graphql"
COINS_PER_USD  = 1000  # 1000 Freecash coins = $1 (standard user rate)

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/en/offers",
}

_GQL_OFFERS_QUERY = """
{
  getOffers(limit: 800) {
    items {
      id
      name
      slug
      description
      coins
      thumbnail
      category
      url
      status
      requirements
      isDesktop
      tasks {
        id
        title
        coins
        type
      }
    }
    meta {
      totalItems
      currentPage
    }
  }
}
"""

# Legacy homepage teaser regex (fallback mode only)
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


def _detect_platform(name: str, slug: str, is_desktop: bool = False) -> str:
    """
    Returns 'desktop', 'android', or 'ios' based on the offer's isDesktop flag
    and name/slug keywords.

    isDesktop=True takes precedence. For mobile offers (isDesktop=False),
    'android'/'ios' keywords in the name/slug decide; otherwise defaults to
    'android' since most unlabelled Freecash offers are multi-platform mobile.
    """
    if is_desktop:
        return "desktop"
    text = f"{name} {slug}".lower()
    if "android" in text:
        return "android"
    if "ios" in text or "iphone" in text or "ipad" in text:
        return "ios"
    return "android"  # default: unlabelled mobile offers


class FreecashCrawler(BaseCrawler):
    PUBLISHER_ID = "freecash"
    PLATFORMS    = ["android", "ios", "desktop"]

    def __init__(self, config: dict):
        super().__init__(config)
        self._session = self._build_session()

    @classmethod
    def from_env(cls, platform: str = "android") -> "FreecashCrawler":
        """
        Constructs a FreecashCrawler.

        Uses authenticated GraphQL if FREECASH_ACCESS_TOKEN is set in .env.
        Falls back to homepage teaser scraper if the token is absent.
        """
        return cls({
            "platform":       platform,
            "access_token":   os.getenv("FREECASH_ACCESS_TOKEN", ""),
            "offers_page_url": os.getenv("FREECASH_OFFERS_PAGE_URL", OFFERS_PAGE_URL),
        })

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(_BASE_HEADERS)
        session.mount(
            "https://",
            HTTPAdapter(max_retries=Retry(
                total=3,
                backoff_factor=1.5,
                status_forcelist=[429, 500, 502, 503, 504],
            )),
        )
        configure_session_proxy(session, self.PUBLISHER_ID)
        return session

    def authenticate(self) -> bool:
        """Sets the fc_access_token cookie when a token is configured."""
        token = self.config.get("access_token", "")
        if token:
            self._session.cookies.set("fc_access_token", token, domain="freecash.com", path="/")
            self.logger.info("Freecash: authenticated via fc_access_token cookie")
            return True
        self.logger.info("Freecash: no access token — will use homepage fallback")
        return False

    def fetch_offers(self) -> Iterator[Offer]:
        """
        Fetches Freecash offers.

        With FREECASH_ACCESS_TOKEN: queries the full GraphQL offer wall (741+
        offers). Offers with no explicit platform indicator are yielded for
        every platform run so they appear in Android, iOS, and Desktop views.

        Without a token: scrapes a small set of teaser cards from the homepage.
        """
        token = self.config.get("access_token", "")
        if token:
            yield from self._fetch_graphql_offers(token)
        else:
            yield from self._fetch_teaser_offers()

    # ── Authenticated GraphQL path ─────────────────────────────────────────────

    def _fetch_graphql_offers(self, token: str) -> Iterator[Offer]:
        platform = self.config.get("platform", "android").lower()
        self._session.cookies.set("fc_access_token", token, domain="freecash.com", path="/")

        try:
            resp = self._session.post(
                FC_GQL_URL,
                json={"query": _GQL_OFFERS_QUERY},
                timeout=60,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            self.on_error(exc, {"phase": "fetch"})
            return

        errors = body.get("errors")
        if errors:
            self.on_error(RuntimeError(errors[0].get("message")), {"phase": "graphql"})
            return

        gql_data = (body.get("data") or {}).get("getOffers", {})
        items    = gql_data.get("items") or []
        total    = (gql_data.get("meta") or {}).get("totalItems", len(items))
        self.logger.info("Freecash GraphQL: %d total offers in API", total)

        count = 0
        for raw in items:
            offer_platform = _detect_platform(
                raw.get("name", ""),
                raw.get("slug", ""),
                raw.get("isDesktop", False),
            )
            if offer_platform != platform:
                continue
            offer = self._norm_graphql(raw, platform)
            if offer:
                yield offer
                count += 1

        self.logger.info("Freecash: %d offers for platform=%s", count, platform)

    def _norm_graphql(self, raw: dict, platform: str) -> Optional[Offer]:
        """Converts a Freecash GraphQL item into a normalised Offer."""
        try:
            coins  = int(raw.get("coins") or 0)
            payout = round(coins / COINS_PER_USD, 2)

            offer_id = str(raw.get("id") or "")
            title    = raw.get("name") or ""
            slug     = raw.get("slug") or offer_id

            desc_html = raw.get("description") or raw.get("requirements") or ""
            description = re.sub(r"<[^>]+>", "", desc_html).strip()

            category = (raw.get("category") or "game").lower()

            tasks = raw.get("tasks") or []
            preview_url = f"{BASE_URL}/o/v2/{slug}" if slug else ""

            return Offer(
                publisher   = self.PUBLISHER_ID,
                offer_id    = offer_id,
                title       = title,
                description = description,
                payout      = payout,
                currency    = "USD",
                category    = category,
                platform    = platform,
                icon_url    = raw.get("thumbnail") or "",
                preview_url = preview_url,
                status      = (raw.get("status") or "active").lower(),
                raw         = {
                    **raw,
                    "source":        "graphql",
                    "coins":         coins,
                    "coins_per_usd": COINS_PER_USD,
                    "task_count":    len(tasks),
                    "is_desktop":    raw.get("isDesktop", False),
                },
            )
        except Exception as exc:
            self.on_error(exc, {"phase": "normalize_graphql", "raw": raw})
            return None

    # ── Unauthenticated homepage-teaser fallback ───────────────────────────────

    def _fetch_teaser_offers(self) -> Iterator[Offer]:
        """Scrapes featured offer cards from the Freecash public homepage."""
        platform = self.config.get("platform", "android").lower()
        url      = self.config.get("offers_page_url", OFFERS_PAGE_URL)

        # Swap to HTML Accept header for the homepage fetch
        self._session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

        try:
            response = self._session.get(url, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            self.on_error(exc, {"phase": "fetch_teaser", "url": url})
            return
        finally:
            self._session.headers.update({"Accept": "application/json"})

        count = 0
        for index, raw in enumerate(self._extract_teaser_cards(response.text), start=1):
            offer = self._norm_teaser(raw, platform, index)
            if offer:
                yield offer
                count += 1

        self.logger.info("Freecash teaser fallback: %d offers (platform=%s)", count, platform)

    def _extract_teaser_cards(self, html_text: str) -> list[dict]:
        offers = []
        seen_titles: set[str] = set()
        for match in _CARD_RE.finditer(html_text):
            title = self._clean_text(match.group("title") or match.group("alt"))
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            offers.append({
                "title":       title,
                "description": self._clean_text(match.group("description")),
                "payout":      f"{match.group('dollars')}.{match.group('cents')}",
                "image":       self._resolve_image_url(match.group("src")),
            })
        return offers

    def _resolve_image_url(self, raw_src: str) -> str:
        src    = html.unescape(raw_src or "")
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

    def _norm_teaser(self, raw: dict, platform: str, index: int) -> Optional[Offer]:
        """Converts a public Freecash teaser card into a normalised Offer."""
        try:
            payout = float(raw.get("payout", 0))
            title  = raw.get("title") or ""
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
            self.on_error(exc, {"phase": "normalize_teaser", "raw": raw})
            return None
