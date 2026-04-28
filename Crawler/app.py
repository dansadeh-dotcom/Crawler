from typing import Optional
from typing import Optional
"""
app.py
-------
The dashboard web server for the TesterUP Offer Wall Viewer.

PURPOSE
    Serves the visual dashboard at http://localhost:5000 and provides the API
    endpoints the dashboard's JavaScript calls to load and compare offer data.

HOW IT WORKS
    - Reads crawl results from the Android/ and iOS/ JSONL files produced by run.py
    - Serves a single-page dashboard (templates/index.html) that lets you filter,
      sort, and compare offers across dates and platforms
    - Proxies live event-breakdown requests to TesterUP's GraphQL API so you can
      see per-event payouts without re-running the crawler

API ENDPOINTS
    GET  /                      → serves the dashboard HTML
    GET  /api/files             → lists all available crawl result files
    GET  /api/offers            → loads offers from a specific file
    GET  /api/offer-events      → fetches live per-event payout breakdown from TesterUP

SECURITY NOTES
    - Credentials are loaded from the .env file — never hard-coded here
    - The server binds to localhost only (not accessible from other machines)
    - debug=False so Flask does not expose stack traces to the browser

HOW TO RUN
    cd "<Google Drive>/Crawler"
    source venv/bin/activate
    python app.py
    → then open http://localhost:5000 in your browser
"""

import json
import os
import requests
from urllib.parse import urlencode

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

# ─── Load credentials from .env ───────────────────────────────────────────────
# .env must exist in the same folder as this script (copy from .env.example).
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

app = Flask(__name__)

# Absolute path to this script's folder — used to locate the Android/ and iOS/
# data directories regardless of where the server is started from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── TesterUP API credentials & endpoints ──────────────────────────────────────
# Loaded from .env — see .env.example for the required keys.
BASE_WEB_URL      = "https://www.testerup.com"
GRAPHQL_URL       = "https://api.v2.testerup.com/graphql/"
TESTERUP_EMAIL    = os.getenv("TESTERUP_EMAIL")
TESTERUP_PASSWORD = os.getenv("TESTERUP_PASSWORD")

# Cached authenticated session — created once on first /api/offer-events call
# and reused for all subsequent requests to avoid re-authenticating every time.
_api_session = None


# ── GraphQL query for per-event offer breakdown ────────────────────────────────
# Fetches the full campaign detail for one offer, including:
#   goals         — the in-game events (e.g. "Complete Level 10", "Open 3 Sacred Shards")
#   targetings    — per-publisher / per-device payout configurations for each goal
#
# Variables:
#   $cid  — campaign ID (= offer_id from the JSONL file)
#   $tid  — targeting ID (optional; narrows results to a specific publisher config)
CAMPAIGN_QUERY = """
query GetCampaign($cid: ID, $tid: ID) {
  campaign(campaignId: $cid, targetingId: $tid) {
    success
    campaign {
      id campaignName
      goals {
        id name sortOrder isStartEvent isInAppPurchase timeLimitHours
        displayNames { languageCode displayName description }
      }
      targetings {
        id publisherId targetDeviceType
        goalConfigurations {
          goalId goal { id name } rewardUsd showToUser sortOrder
          rewards { reward currencyCode }
        }
      }
    }
  }
}
"""


def _get_session() -> requests.Session:
    """
    Returns an authenticated HTTP session for TesterUP's private API.

    Authentication uses TesterUP's web login flow (same as logging in via the browser):
      Step 1 — Fetch a CSRF token to prevent request forgery attacks
      Step 2 — POST email + password + CSRF token to the credentials endpoint
      Step 3 — Fetch the session object, which contains the Bearer access token

    The session is cached in the module-level _api_session variable so we only
    authenticate once per server lifetime (not on every dashboard click).

    Returns:
        An authenticated requests.Session with the Authorization header set.

    Raises:
        Exception if authentication fails (e.g. wrong credentials or API down).
    """
    global _api_session
    if _api_session:
        return _api_session

    s = requests.Session()

    # Step 1: get CSRF security token
    csrf = s.get(f"{BASE_WEB_URL}/api/auth/csrf", timeout=15).json()["csrfToken"]

    # Step 2: submit credentials
    s.post(
        f"{BASE_WEB_URL}/api/auth/callback/credentials",
        data=urlencode({
            "email":       TESTERUP_EMAIL,
            "password":    TESTERUP_PASSWORD,
            "csrfToken":   csrf,
            "redirect":    "false",
            "newUser":     "false",
            "callbackUrl": "https://www.testerup.com/dashboard?provider=email&method=login",
            "json":        "true",
        }),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )

    # Step 3: extract the Bearer token and attach it to all future requests
    data  = s.get(f"{BASE_WEB_URL}/api/auth/session", timeout=15).json()
    token = data.get("user", {}).get("accessToken") or data.get("accessToken")
    s.headers["Authorization"] = f"Bearer {token}"

    _api_session = s
    return s


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """
    Serves the main dashboard HTML page (templates/index.html).
    All subsequent data is loaded asynchronously by the page's JavaScript.
    """
    return render_template("index.html")


@app.route("/api/files")
def list_files():
    """
    Scans the Android/ and iOS/ subdirectories and returns metadata for every
    valid crawl result file found.

    The dashboard uses this response to populate its Publisher, Platform, and
    Date dropdown menus on load.

    Skips:
      - Files that are 0 bytes (produced by failed/aborted crawl runs)
      - Files that don't follow the {publisher}_offers_{timestamp}.jsonl naming convention

    Returns JSON array of objects, each with:
      publisher   — e.g. "testerup"
      platform    — "Android" or "iOS"
      date        — "YYYYMMDD" (used to group files by day in the dropdown)
      timestamp   — "YYYYMMDD_HHMMSS" (used to load the exact file)
    """
    files = []
    for platform in ["Android", "iOS", "Desktop"]:
        platform_dir = os.path.join(BASE_DIR, platform)
        if not os.path.exists(platform_dir):
            continue

        for fname in sorted(os.listdir(platform_dir), reverse=True):
            if not fname.endswith(".jsonl"):
                continue
            stem = fname[:-6]   # strip ".jsonl"
            if "_offers_" not in stem:
                continue

            # Skip empty files — these come from crawl runs that failed after
            # creating the output file but before writing any data
            fpath = os.path.join(platform_dir, fname)
            if os.path.getsize(fpath) == 0:
                continue

            publisher, ts = stem.split("_offers_", 1)
            files.append({
                "publisher": publisher,
                "platform":  platform,
                "date":      ts[:8],    # "YYYYMMDD" — shown in the date dropdown
                "timestamp": ts,        # full "YYYYMMDD_HHMMSS" — used to load the file
            })

    return jsonify(files)


@app.route("/api/offers")
def get_offers():
    """
    Reads offers from a specific JSONL result file and returns only those that
    match the selected platform.

    Background: The TesterUP API returns both Android and iOS offers in a single
    response, so both are saved to each platform folder. This endpoint filters
    the file by the offer's targetDeviceType field so the dashboard shows only
    Android offers when Android is selected, and vice versa.

    Deduplication: If the same offer_id appears more than once in a file (which
    can happen in rare edge cases), only the first occurrence is returned.

    Query parameters (all required):
      platform   — "Android" or "iOS"
      publisher  — e.g. "testerup"
      timestamp  — e.g. "20260414_073912"

    Returns JSON array of normalised offer objects.
    Returns 400 if parameters are missing, 404 if the file doesn't exist.
    """
    platform  = request.args.get("platform")
    publisher = request.args.get("publisher")
    timestamp = request.args.get("timestamp")

    if not all([platform, publisher, timestamp]):
        return jsonify({"error": "Missing required parameters: platform, publisher, timestamp"}), 400

    filepath = os.path.join(BASE_DIR, platform, f"{publisher}_offers_{timestamp}.jsonl")
    if not os.path.exists(filepath):
        return jsonify({"error": f"File not found: {filepath}"}), 404

    # Parse every line in the JSONL file, skipping blank lines and malformed JSON
    raw_offers = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    raw_offers.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # skip corrupted lines silently

    # Filter: keep only offers matching the requested platform.
    # Checks (in order): raw.targetDeviceType (TesterUP), normalised platform field,
    # then falls back to showing the offer if no platform info is available.
    device_filter = platform.lower()
    seen_ids: dict = {}
    for offer in raw_offers:
        raw_device = (offer.get("raw") or {}).get("targetDeviceType", "").lower()
        norm_platform = offer.get("platform", "").lower()
        # Use whichever field has a value; if neither does, include the offer
        device_type = raw_device or norm_platform
        if device_type and device_type != device_filter:
            continue
        oid = offer.get("offer_id")
        if oid not in seen_ids:   # keep first occurrence only
            seen_ids[oid] = offer

    return jsonify(list(seen_ids.values()))


@app.route("/api/offer-events")
def get_offer_events():
    """
    Fetches the per-event payout breakdown for a single offer, live from TesterUP's API.

    This is called when a user clicks on an offer card in the dashboard. It returns
    the list of in-game events the user must complete to earn the offer payout,
    along with the USD value of each event.

    The response merges two sources from TesterUP's GraphQL schema:
      - campaign.goals        — event metadata (name, sort order, type)
      - campaign.targetings   — payout configurations per publisher/device

    When the same goal appears in multiple targeting configurations (e.g. different
    countries or publishers), the highest USD payout seen is kept.

    Query parameters:
      offer_id      — the offer's campaign ID (e.g. "67")
      targeting_id  — optional; if provided, narrows the query to a specific publisher
                      targeting config. Empty string is treated as absent (→ null in GraphQL).

    Returns JSON object:
      {
        "title":  "RAID: Shadow Legends",
        "events": [
          { "name": "Complete Tutorial", "payout": 0.10, "sortOrder": 1, ... },
          { "name": "Reach Level 30",    "payout": 2.50, "sortOrder": 5, ... }
        ]
      }
    Events are sorted by sortOrder (game progression order, not payout amount).
    Returns { "events": [] } with no error if the offer has no breakdown available.
    """
    offer_id     = request.args.get("offer_id")
    # Convert empty string → None so the GraphQL variable gets null, not ""
    targeting_id = request.args.get("targeting_id") or None

    if not offer_id:
        return jsonify({"error": "Missing required parameter: offer_id"}), 400

    try:
        session = _get_session()
        resp = session.post(
            GRAPHQL_URL,
            json={
                "query":         CAMPAIGN_QUERY,
                "variables":     {"cid": offer_id, "tid": targeting_id},
                "operationName": "GetCampaign",
            },
            timeout=30,
        )
        data      = resp.json()
        camp_data = (data.get("data") or {}).get("campaign") or {}

        if not camp_data.get("success"):
            return jsonify({"events": [], "title": ""})

        campaign = camp_data["campaign"]

        # ── Build goal_id → display info map ──────────────────────────────────
        # TesterUP stores human-readable event names in displayNames (one per language).
        # We prefer English; fall back to the internal name if English is missing.
        goals_map: dict = {}
        for g in (campaign.get("goals") or []):
            dn_list = g.get("displayNames") or []
            display = next(
                (d["displayName"] for d in dn_list
                 if d.get("languageCode") == "en" and d.get("displayName")),
                None,
            ) or g["name"]
            goals_map[g["id"]] = {
                "display":         display,
                "sortOrder":       g.get("sortOrder", 0),
                "isStartEvent":    g.get("isStartEvent", False),
                "isInAppPurchase": g.get("isInAppPurchase", False),
                "timeLimitHours":  g.get("timeLimitHours"),
            }

        # ── Collect best payout per goal across all targeting configurations ──
        # A goal can appear in multiple targetings (different publishers, countries).
        # We keep only the highest USD payout seen for each goal.
        best: dict = {}
        for targ in (campaign.get("targetings") or []):
            for gc in (targ.get("goalConfigurations") or []):
                if not gc.get("showToUser"):
                    continue   # skip goals hidden from end users

                goal_id  = gc.get("goalId") or ((gc.get("goal") or {}).get("id"))
                reward   = gc.get("rewardUsd") or 0
                currency = "USD"

                # Use the explicit per-currency reward if available
                for r in (gc.get("rewards") or []):
                    if r.get("currencyCode") == "USD":
                        reward   = r["reward"]
                        currency = "USD"
                        break

                if goal_id not in best or reward > best[goal_id]["payout"]:
                    best[goal_id] = {
                        "id":        goal_id,
                        "payout":    reward,
                        "currency":  currency,
                        "sortOrder": gc.get("sortOrder") or 0,
                    }

        # ── Merge payout data with display metadata ────────────────────────────
        events = []
        for goal_id, config in best.items():
            meta = goals_map.get(goal_id, {})
            events.append({
                "id":              goal_id,
                "name":            meta.get("display", goal_id),
                "payout":          config["payout"],
                "currency":        config["currency"],
                "sortOrder":       meta.get("sortOrder", config["sortOrder"]),
                "isStartEvent":    meta.get("isStartEvent", False),
                "isInAppPurchase": meta.get("isInAppPurchase", False),
                "timeLimitHours":  meta.get("timeLimitHours"),
            })

        # Sort by game progression order (lower sortOrder = earlier event)
        events.sort(key=lambda x: x["sortOrder"])
        return jsonify({"events": events, "title": campaign.get("campaignName", "")})

    except Exception as e:
        return jsonify({"events": [], "error": str(e)})


if __name__ == "__main__":
    print("✅  Dashboard running at http://localhost:5000")
    app.run(debug=False, port=5000, host="127.0.0.1")
