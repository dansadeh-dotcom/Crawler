from typing import Optional
from typing import Optional
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

SCHEDULING
    This script runs automatically every day at 7:00 AM via Claude's scheduled
    task system. You can also run it manually at any time.
"""

import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv

# ── Import all crawler classes ─────────────────────────────────────────────────
from testerup_crawler  import TesterUpCrawler
from kashkick_crawler  import KashkickCrawler
from freecash_crawler  import FreecashCrawler
from swagbucks_crawler import SwagbucksCrawler

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
    SwagbucksCrawler,
]

# Publisher-specific platform overrides.
# Freecash should run on android, ios, and desktop/web snapshots.
PLATFORM_OVERRIDES = {
    FreecashCrawler.PUBLISHER_ID: ["android", "ios", "desktop"],
}

# Output root — Android/ and iOS/ subfolders are created here automatically
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_all():
    """
    Runs a crawl for every registered publisher × platform combination.

    For each publisher:
      - Reads credentials from .env via the crawler's from_env() classmethod
      - Skips cleanly (with a warning) if credentials are missing
      - Writes results to {platform_folder}/{publisher}_offers_{timestamp}.jsonl

    Prints a human-readable summary when all crawls finish.
    """
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
            platform_folder = {"ios": "iOS", "desktop": "Desktop"}.get(platform, "Android")
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

                logging.info("✅ %s: %d offers → %s", key, count, fname)
                results[key] = {"status": "ok", "count": count, "file": fname}

            except Exception as exc:
                logging.exception("Crawl failed: %s", key)
                results[key] = {"status": "error", "error": str(exc)}
                # Remove empty output files so the dashboard doesn't show phantom entries
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


if __name__ == "__main__":
    run_all()
