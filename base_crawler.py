"""
base_crawler.py
----------------
Defines the shared data model and abstract interface that all publisher crawlers
must implement.

PURPOSE
    Provides a common contract so that different publisher crawlers (TesterUP,
    IronSource, Tapjoy, etc.) all produce the same Offer structure and can be
    plugged into the same run.py orchestrator without changing any other code.

COMPONENTS
    Offer       — a dataclass representing one normalised offer from any publisher
    BaseCrawler — an abstract base class every publisher crawler must extend

EXTENDING
    To add a new publisher:
      1. Create {publisher}_crawler.py
      2. Subclass BaseCrawler, set PUBLISHER_ID and PLATFORMS
      3. Implement from_env(), authenticate(), fetch_offers()
      4. Add the class to CRAWLER_CLASSES in run.py
      5. Add credentials to .env (see .env.example)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from collections.abc import Iterator
import logging
import os

logger = logging.getLogger(__name__)


def resolve_proxy_url(publisher_id: Optional[str] = None) -> Optional[str]:
    """
    Resolves proxy URL from environment.

    Resolution order:
      1) {PUBLISHER}_PROXY_URL (e.g. TESTERUP_PROXY_URL)
      2) CRAWLER_PROXY_URL (global fallback)
    """
    publisher_proxy = ""
    if publisher_id:
        publisher_proxy = os.getenv(f"{publisher_id.upper()}_PROXY_URL", "")

    global_proxy = os.getenv("CRAWLER_PROXY_URL", "")
    proxy = (publisher_proxy or global_proxy).strip()
    return proxy or None


def configure_session_proxy(session, publisher_id: Optional[str] = None) -> Optional[str]:
    """
    Applies explicit proxy routing to a requests Session if configured.
    """
    proxy = resolve_proxy_url(publisher_id)
    # Avoid accidental proxying from parent shell env; use only explicit crawler vars.
    session.trust_env = False
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    return proxy


@dataclass
class Offer:
    """
    A normalised offer object shared across all publisher crawlers.

    All fields use common names regardless of which publisher produced the offer,
    so the dashboard and any future analytics can treat all offers uniformly.

    The 'raw' field always contains the original unmodified API response, so
    no information is lost even if new fields are added to the API in the future.

    Fields:
        publisher       Publisher identifier, e.g. "testerup"
        offer_id        Publisher's internal offer ID (string to handle all formats)
        title           Display name of the offer (game/app name)
        description     Human-readable description of what the user must do
        payout          Total USD payout for completing all required events
        currency        Payout currency code, always "USD" for TesterUP
        category        Offer category, e.g. "Mobile Game", "story"
        platform        Target device platform: "android", "ios", or "web"
        countries       ISO-3166 country codes where this offer is available
        requirements    Human-readable completion instructions
        icon_url        URL of the offer's icon/thumbnail image
        preview_url     URL of the tracking/preview link
        status          Offer lifecycle state: "active", "paused", or "expired"
        daily_cap       Maximum conversions allowed per day (None = unlimited)
        total_cap       Maximum total conversions allowed (None = unlimited)
        raw             Original unmodified API response dict
        crawled_at      UTC ISO-8601 timestamp of when this offer was fetched
    """
    publisher: str
    offer_id: str
    title: str
    description: str
    payout: float                               # total USD value
    currency: str = "USD"
    category: str = ""
    platform: str = ""                          # "android", "ios", "web"
    countries: list[str] = field(default_factory=list)
    requirements: str = ""
    icon_url: str = ""
    preview_url: str = ""
    status: str = "active"                      # "active" | "paused" | "expired"
    daily_cap: Optional[int] = None
    total_cap: Optional[int] = None
    raw: dict = field(default_factory=dict)     # original API response, unmodified
    crawled_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )

    def to_dict(self) -> dict:
        """
        Converts this Offer to a plain dictionary for JSON serialisation.
        Used by run.py when writing each offer as a line in the .jsonl output file.
        """
        return asdict(self)


class BaseCrawler(ABC):
    """
    Abstract base class that every publisher crawler must extend.

    Defines the minimum interface required for a crawler to be plugged into
    the run.py orchestration loop. Subclasses must implement three methods:
    from_env(), authenticate(), and fetch_offers().

    Built-in helpers (on_error, healthcheck) can be overridden in subclasses
    for custom alerting or more sophisticated health checks.

    Usage:
        crawler = TesterUpCrawler.from_env(platform="android")
        for offer in crawler.fetch_offers():
            save(offer)

    TO ADD A NEW PUBLISHER:
        1. Create {publisher}_crawler.py
        2. Subclass BaseCrawler
        3. Set PUBLISHER_ID and PLATFORMS class attributes
        4. Implement from_env(), authenticate(), and fetch_offers()
        5. Add the class to CRAWLER_CLASSES in run.py
        6. Add credentials to .env (see .env.example)
    """

    PUBLISHER_ID: str       = ""                  # e.g. "testerup" — override in subclass
    PLATFORMS:    list[str] = ["android", "ios"]  # platforms this crawler supports

    def __init__(self, config: dict):
        """
        Initialises the crawler with the given configuration dictionary.

        Args:
            config: Dict containing credentials and runtime options.
                    See class docstring for expected keys.
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    @classmethod
    def from_env(cls, platform: str = "android") -> "BaseCrawler":
        """
        Constructs a crawler instance from environment variables.

        Override in each subclass to read the appropriate env vars and build
        the config dict. Raise EnvironmentError if required credentials are
        missing so run.py can skip the crawler gracefully.

        Args:
            platform: "android" or "ios" — the platform to crawl for.

        Returns:
            A configured crawler instance ready to call fetch_offers() on.

        Raises:
            EnvironmentError: If required credentials are missing from .env.
        """
        raise NotImplementedError(f"{cls.__name__} must implement from_env()")

    # ── Required interface — must be implemented by every subclass ─────────────

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Performs the authentication flow required by this publisher's API.

        Called automatically by fetch_offers() if no token exists yet.
        Can also be called manually for a healthcheck.

        Returns:
            True if authentication succeeded and the session is ready to use.
            False if authentication failed (wrong credentials, API down, etc.).
        """

    @abstractmethod
    def fetch_offers(self) -> Iterator[Offer]:
        """
        Fetches all available offers from the publisher's API and yields them
        one at a time as normalised Offer objects.

        Implementations should handle:
          - Authentication (call authenticate() if not yet done)
          - Pagination (keep fetching pages until there are no more)
          - Rate limiting (respect self.config["rate_limit"] if set)
          - Error handling (catch exceptions, log them, and stop gracefully)

        Yields:
            One Offer object per item returned by the API.
        """

    # ── Optional hooks — override in subclasses if needed ──────────────────────

    def on_error(self, error: Exception, context: dict) -> None:
        """
        Called whenever the crawler encounters an error during authentication
        or data fetching.

        Default implementation logs the error. Override this in a subclass to
        add alerting (e.g. send a Slack message, write to a monitoring system).

        Args:
            error:   The exception that was raised.
            context: A dict with extra info, e.g. {"phase": "login"} or
                     {"phase": "normalize", "raw": {...}}.
        """
        self.logger.error(
            "Error in %s: %s | context=%s",
            self.PUBLISHER_ID, error, context
        )

    def healthcheck(self) -> bool:
        """
        Quickly verifies that this publisher's API is reachable and credentials work.

        Called by run.py before starting a crawl to avoid creating empty output
        files when the API is down or credentials have expired.

        Default implementation simply calls authenticate(). Override if a
        cheaper/faster check is available (e.g. a ping endpoint).

        Returns:
            True if the API is reachable and authentication succeeded.
        """
        try:
            return self.authenticate()
        except Exception as e:
            self.on_error(e, {"phase": "healthcheck"})
            return False
