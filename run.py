"""
run.py
-------
Main entry point for the offer wall crawler.

PURPOSE
    Fetches the live offer wall from all registered publishers for both
    Android, desktop and iOS platforms, and saves results as timestamped JSONL files.
    These files are read by app.py to visualise and compare offer walls.

HOW TO ADD A NEW PUBLISHER
    1. Create {publisher}_crawler.py (copy kashkick_crawler.py as a template)
    2. Implement from_env(), authenticate(), and fetch_offers()
    3. Import the class and add it to CRAWLER_CLASSES below — that's it

HOW TO RUN
    cd "<Google Drive>/Crawler (1)"
    source venv/bin/activate
    python run.py

OUTPUT FILES
    Android/{publisher}_offers_YYYYMMDD_HHMMSS.jsonl
    iOS/{publisher}_offers_YYYYMMDD_HHMMSS.jsonl
    Desktop/{publisher}_offers_YYYYMMDD_HHMMSS.jsonl

SCHEDULING
    This script runs automatically every day at 7:00 AM via Claude's scheduled
    task system. You can also run it manually at any time.
"""

import json
import logging
import os
from datetime import datetime

import requests
from dotenv import load_dotenv

# ── Import all crawler classes ─────────────────────────────────────────────────
from testerup_crawler  import TesterUpCrawler
from kashkick_crawler  import KashkickCrawler
from freecash_crawler  import FreecashCrawler
from base_crawler import resolve_proxy_url

# ── Load credentials ───────────────────────────────────────────────────────────
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(levelname)-8s  %(message)s",
)

# ── Crawler registry ───────────────────────────────────────────────────────────
# To add a new publisher: create {name}_crawler.py and add the class here.
# Each class must implement from_env(platform) → BaseCrawler.
CRAWLER_CLASSES = [
    TesterUpCrawler,
    KashkickCrawler,
    FreecashCrawler,
    # SwagbucksCrawler disabled — OFFERS_URL is a placeholder; re-enable once endpoint is known
]

# Publisher-specific platform overrides.
# Freecash should run on android, ios, and desktop/web snapshots.
PLATFORM_OVERRIDES = {
    FreecashCrawler.PUBLISHER_ID: ["android", "ios", "desktop"],
}

# Output root — Android/ and iOS/ subfolders are created here automatically
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def preflight_ip_check() -> bool:
    """
    Logs public IP/country before crawling and optionally enforces US egress.

    Env:
      - REQUIRE_US_IP=true|false
      - EXPECTED_COUNTRY_CODE=US
      - CRAWLER_PROXY_URL / {PUBLISHER}_PROXY_URL
    """
    expected_country = os.getenv("EXPECTED_COUNTRY_CODE", "US").strip().upper() or "US"
    require_country = _env_flag("REQUIRE_US_IP", default=False)

    session = requests.Session()
    session.trust_env = False
    proxy = resolve_proxy_url()
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})

    ip = "unknown"
    country = "unknown"
    try:
        response = session.get("https://api.country.is/", timeout=15)
        response.raise_for_status()
        payload = response.json()
        ip = str(payload.get("ip") or ip)
        country = str(payload.get("country") or country).upper()
    except Exception as exc:
        logging.warning("IP preflight via api.country.is failed: %s", exc)
        try:
            response = session.get("https://ipinfo.io/json", timeout=15)
            response.raise_for_status()
            payload = response.json()
            ip = str(payload.get("ip") or ip)
            country = str(payload.get("country") or country).upper()
        except Exception as ipify_exc:
            logging.warning("IP preflight via ipinfo.io failed: %s", ipify_exc)

    logging.info(
        "Network preflight: ip=%s country=%s expected_country=%s proxy_configured=%s require_country=%s",
        ip,
        country,
        expected_country,
        bool(proxy),
        require_country,
    )

    if require_country and country != expected_country:
        logging.error(
            "Stopping crawl because egress country is '%s' (expected '%s').",
            country,
            expected_country,
        )
        return False
    return True


def run_all():
    """
    Runs a crawl for every registered publisher × platform combination.

    For each publisher:
      - Reads credentials from .env via the crawler's from_env() classmethod
      - Skips cleanly (with a warning) if credentials are missing
      - Writes results to {platform_folder}/{publisher}_offers_{timestamp}.jsonl

    Prints a human-readable summary when all crawls finish.
    """
    if not preflight_ip_check():
        print("\n── Crawl summary ───────────────────────────────────────────────")
        print("  ❌  preflight                      blocked by country check")
        print("────────────────────────────────────────────────────────────────\n")
        return

    results = {}

    for CrawlerClass in CRAWLER_CLASSES:
        pub = CrawlerClass.PUBLISHER_ID

        platforms = PLATFORM_OVERRIDES.get(pub, CrawlerClass.PLATFORMS)
        for platform in platforms:
            key = f"{pub}/{platform}"
            logging.info("▶  Starting: %s / %s", pub, platform)

            # Build the crawler from env vars; skip cleanly if credentials are missing
            try:
                crawler = CrawlerClass.from_env(platform=platform)
            except (OSError, NotImplementedError) as exc:
                logging.warning("⚠️  Skipping %s — %s", key, exc)
                results[key] = {"status": "skipped", "reason": str(exc)}
                continue

            # Prepare output file
            # All publishers share Android / iOS / Desktop folders.
            # Publisher is identified by the filename prefix (e.g. freecash_offers_...).
            platform_folder = {"android": "Android", "ios": "iOS", "desktop": "Desktop"}.get(platform, platform)
            output_dir = os.path.join(SCRIPT_DIR, platform_folder)
            os.makedirs(output_dir, exist_ok=True)

            ts    = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            fname = os.path.join(output_dir, f"{pub}_offers_{ts}.jsonl")

            try:
                count = 0
                with open(fname, "w") as f:
                    for offer in crawler.fetch_offers():
                        f.write(json.dumps(offer.to_dict()) + "\n")
                        count += 1
                        if count % 100 == 0:
                            logging.info("  %d offers saved…", count)

                # Remove empty output files so the dashboard doesn't show phantom entries
                if os.path.exists(fname) and os.path.getsize(fname) == 0:
                    os.remove(fname)
                    logging.info("⏭️  %s: 0 offers, file removed", key)
                    results[key] = {"status": "skipped", "reason": "0 offers returned"}
                else:
                    logging.info("✅ %s: %d offers → %s", key, count, fname)
                    results[key] = {"status": "ok", "count": count, "file": fname}

            except Exception as exc:
                logging.exception("Crawl failed: %s", key)
                results[key] = {"status": "error", "error": str(exc)}
                if os.path.exists(fname) and os.path.getsize(fname) == 0:
                    os.remove(fname)

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n── Crawl summary ───────────────────────────────────────────────")
    for key, r in results.items():
        if r["status"] == "ok":
            print(f"  ✅  {key:30s}  {r['count']} offers")
        elif r["status"] == "skipped":
            print(f"  ⏭️   {key:30s}  skipped ({r['reason'][:60]})")
        else:
            print(f"  ❌  {key:30s}  ERROR: {r['error']}")
    print("────────────────────────────────────────────────────────────────\n")

    # ── Auto-upload to Vercel Blob ────────────────────────────────────────────
    # After crawling, upload files to Blob so the dashboard can see them
    if os.getenv("BLOB_READ_WRITE_TOKEN"):
        logging.info("Uploading to Vercel Blob...")
        try:
            import subprocess
            result = subprocess.run(
                ["node", "blob-upload.js"],
                cwd=SCRIPT_DIR,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.stdout:
                logging.info("Blob upload output:\n%s", result.stdout.strip())
            if result.returncode != 0:
                logging.warning("Blob upload failed (exit %d):\n%s", result.returncode, result.stderr.strip())
        except Exception as e:
            logging.warning("Failed to upload to Blob: %s", e)


if __name__ == "__main__":
    run_all()
