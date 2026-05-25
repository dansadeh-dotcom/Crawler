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
import time
import requests
from urllib.parse import urlencode, unquote

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

try:
    from blob_utils import list_blob_files, download_blob_file
    BLOB_AVAILABLE = True
except Exception as e:
    print(f"Warning: Blob utils not available: {e}")
    BLOB_AVAILABLE = False

# ─── Load credentials from .env ───────────────────────────────────────────────
# .env must exist in the same folder as this script (copy from .env.example).
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

app = Flask(__name__)

# ── TesterUP API credentials & endpoints ──────────────────────────────────────
# Loaded from .env — see .env.example for the required keys.
BASE_WEB_URL      = "https://www.testerup.com"
GRAPHQL_URL       = "https://api.v2.testerup.com/graphql/"
TESTERUP_EMAIL    = os.getenv("TESTERUP_EMAIL")
TESTERUP_PASSWORD = os.getenv("TESTERUP_PASSWORD")

# Folder name → display name mapping used in both /api/files and /api/offers
_PLATFORM_FOLDER_MAP = {
    "Android": "Android",
    "iOS": "iOS",
    "Desktop": "Desktop",
    "Freecash mobile": "Freecash mobile",
    "freecash desktop": "freecash desktop",
    "Kashkick": "Kashkick",
    "swagbucks": "swagbucks",
    "testerup": "testerup",
}

# Cached authenticated session — re-created when token is older than _SESSION_TTL
_api_session = None
_session_created_at: float = 0.0
_SESSION_TTL = 50 * 60  # 50 minutes — TesterUP tokens expire after ~1 hour


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

    Re-authenticates if the cached session is older than _SESSION_TTL (50 min).

    Auth flow (3 steps — /api/auth/csrf returns 403, so we load the homepage instead):
      Step 1 — GET homepage to receive the __Host-next-auth.csrf-token cookie
      Step 2 — POST email + password + CSRF token to the credentials endpoint
      Step 3 — GET session to extract the Bearer access token

    Raises:
        RuntimeError if authentication fails.
    """
    global _api_session, _session_created_at
    if _api_session and (time.time() - _session_created_at) < _SESSION_TTL:
        return _api_session

    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    })

    # Step 1: load homepage to receive CSRF cookie
    s.get(f"{BASE_WEB_URL}/", timeout=15)
    raw_cookie = s.cookies.get("__Host-next-auth.csrf-token", "")
    if not raw_cookie:
        raise RuntimeError("CSRF cookie not set after loading TesterUP homepage")
    csrf = unquote(raw_cookie).split("|")[0]

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

    # Step 3: extract Bearer token
    data  = s.get(f"{BASE_WEB_URL}/api/auth/session", timeout=15).json()
    token = data.get("user", {}).get("accessToken") or data.get("accessToken")
    if not token:
        raise RuntimeError(f"Failed to obtain TesterUP access token: {data}")
    s.headers["Authorization"] = f"Bearer {token}"

    _api_session = s
    _session_created_at = time.time()
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
    Lists crawl result files from Vercel Blob storage.

    The dashboard uses this response to populate its Publisher, Platform, and
    Date dropdown menus on load.

    Skips:
      - Files that don't follow the {publisher}_offers_{timestamp}.jsonl naming convention

    Returns JSON array of objects, each with:
      publisher   — e.g. "testerup"
      platform    — "Android", "iOS", "freecash desktop", or "Freecash mobile"
      date        — "YYYYMMDD" (used to group files by day in the dropdown)
      timestamp   — "YYYYMMDD_HHMMSS" (used to load the exact file)
    """
    files = []
    try:
        if not BLOB_AVAILABLE:
            return jsonify({"error": "Blob storage not configured"}), 503
        
        # List all files in Blob storage
        blob_files = list_blob_files()
        
        # Group by platform folder
        for blob_file in blob_files:
            pathname = blob_file.get("pathname", "")
            if not pathname.endswith(".jsonl"):
                continue
            
            # Extract folder and filename
            if "/" not in pathname:
                continue
            
            platform_folder, fname = pathname.rsplit("/", 1)
            stem = fname[:-6]  # strip ".jsonl"
            
            if "_offers_" not in stem:
                continue
            
            publisher, ts = stem.split("_offers_", 1)
            
            platform_name = _PLATFORM_FOLDER_MAP.get(platform_folder, platform_folder)
            
            files.append({
                "publisher": publisher,
                "platform": platform_name,
                "date": ts[:8],  # "YYYYMMDD"
                "timestamp": ts,  # full "YYYYMMDD_HHMMSS"
                "blob_pathname": pathname,  # for later use in get_offers
            })
        
        # Sort by timestamp descending
        files.sort(key=lambda x: x["timestamp"], reverse=True)
        
    except Exception as e:
        print(f"Error listing Blob files: {e}")
        return jsonify({"error": str(e)}), 500
    
    return jsonify(files)


@app.route("/api/offers")
def get_offers():
    """
    Reads offers from a specific JSONL result file in Vercel Blob and returns 
    only those that match the selected platform.

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

    platform_folder = _PLATFORM_FOLDER_MAP.get(platform, platform)
    blob_pathname = f"{platform_folder}/{publisher}_offers_{timestamp}.jsonl"
    
    # Download file from Blob
    if not BLOB_AVAILABLE:
        return jsonify({"error": "Blob storage not configured"}), 503
    
    file_content = download_blob_file(blob_pathname)
    if file_content is None:
        return jsonify({"error": f"File not found in Blob: {blob_pathname}"}), 404

    # Parse every line in the JSONL content
    raw_offers = []
    try:
        for line in file_content.decode("utf-8").split("\n"):
            line = line.strip()
            if line:
                try:
                    raw_offers.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # skip corrupted lines silently
    except Exception as e:
        print(f"Error parsing JSONL: {e}")
        return jsonify({"error": f"Error parsing JSONL: {str(e)}"}), 500

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
