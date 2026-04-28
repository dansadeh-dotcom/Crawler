# System Architecture — TesterUP Offer Wall Crawler & Dashboard

## Overview

The system has two independent parts that work together:

1. **The Crawler** — runs on a schedule, fetches live offer data, saves it to files
2. **The Dashboard** — reads those files and serves a visual interface in the browser

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AUTOMATED DAILY CRAWL                              │
│                                                                             │
│   [Claude Scheduled Task]  ──── 7:00 AM daily ────►  [run.py]              │
└──────────────────────────────────────────────────────────┬──────────────────┘
                                                           │
                    ┌──────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                            CRAWLER LAYER                                      │
│                                                                               │
│   run.py                                                                      │
│   ├── Loads credentials from .env                                             │
│   ├── For each platform (Android, iOS):                                       │
│   │     └── TesterUpCrawler (testerup_crawler.py)                            │
│   │           ├── authenticate()  ─────────────────────────►  TesterUP API   │
│   │           │     Step 1: GET  /api/auth/csrf                               │
│   │           │     Step 2: POST /api/auth/callback/credentials               │
│   │           │     Step 3: GET  /api/auth/session → Bearer token            │
│   │           │                                                               │
│   │           └── fetch_offers()  ─────────────────────────►  TesterUP API   │
│   │                 POST https://api.v2.testerup.com/graphql/                 │
│   │                 Query: UserContent (offers + stories)                     │
│   │                                                                           │
│   └── Writes JSONL files:                                                    │
│         Android/testerup_offers_YYYYMMDD_HHMMSS.jsonl                        │
│         iOS/testerup_offers_YYYYMMDD_HHMMSS.jsonl                            │
└───────────────────────────────────────────────┬───────────────────────────────┘
                                                │
                          Google Drive syncs files to all collaborators
                                                │
                    ┌───────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                         DASHBOARD LAYER (app.py)                              │
│                                                                               │
│   Flask web server on http://localhost:5000                                   │
│                                                                               │
│   GET  /                   → renders templates/index.html                     │
│   GET  /api/files          → scans Android/ + iOS/ dirs, returns file list    │
│   GET  /api/offers         → reads a specific .jsonl, filters by platform     │
│   GET  /api/offer-events   → live GraphQL call to TesterUP for event details  │
│                                    │                                          │
│                                    ▼                                          │
│                              TesterUP API                                     │
│                              campaign(campaignId, targetingId)                │
│                              → goals + targetings + payouts                   │
└───────────────────────────────────────────────┬───────────────────────────────┘
                                                │
                                                ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                           BROWSER UI (index.html)                             │
│                                                                               │
│   Vanilla JavaScript single-page dashboard                                    │
│                                                                               │
│   Key data structures:                                                        │
│     offerMap          offer_id → offer object (for fast lookups)              │
│     panelOffers       {1: [...], 2: [...]} offers currently shown             │
│     selectedForCompare  Map of "panelN:offer_id" → offer (compare mode)       │
│                                                                               │
│   Panels:                                                                     │
│     Panel 1 (always visible) — primary offer wall view                        │
│     Panel 2 (compare mode)  — second date/publisher for side-by-side          │
│                                                                               │
│   On load: auto-selects TesterUP / Android / yesterday's date                 │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
Crawler/
│
├── .env                    ← credentials (not shared/committed)
├── .env.example            ← template for new users to copy
├── .gitignore              ← prevents credentials & venv from being committed
├── requirements.txt        ← exact Python dependency versions
│
├── run.py                  ← CRAWLER entry point — run this to fetch new data
├── testerup_crawler.py     ← TesterUP-specific API logic (auth + GraphQL)
├── base_crawler.py         ← shared Offer model + BaseCrawler abstract class
│
├── app.py                  ← DASHBOARD server — run this to open the UI
├── templates/
│   └── index.html          ← single-page dashboard (HTML + CSS + JS, ~700 lines)
│
├── Android/                ← crawl results for Android
│   └── testerup_offers_YYYYMMDD_HHMMSS.jsonl
├── iOS/                    ← crawl results for iOS
│   └── testerup_offers_YYYYMMDD_HHMMSS.jsonl
│
├── venv/                   ← Python virtual environment (machine-specific)
│
└── docs/
    ├── ARCHITECTURE.md     ← this file
    └── USER_MANUAL.md      ← guide for dashboard-only users
```

---

## Data Flow

### Crawl flow (run.py → JSONL files)

```
TesterUP API
    │
    │  GraphQL: UserContent query
    │  → { offers: [...], stories: [...] }
    │
    ▼
TesterUpCrawler._norm()
    │
    │  Converts each raw API item → Offer dataclass
    │  Preserves original response in offer.raw
    │
    ▼
run.py: open(output_file, "w")
    │
    │  Writes one JSON line per offer:
    │  {"publisher":"testerup","offer_id":"67","title":"RAID:...","raw":{...}}
    │
    ▼
Android/testerup_offers_20260414_073912.jsonl
```

### Dashboard flow (browser → JSONL files → TesterUP API)

```
Browser loads http://localhost:5000
    │
    ├── GET /api/files
    │       Scans Android/ + iOS/, returns list of available dates
    │       JS uses this to populate dropdowns + auto-select yesterday
    │
    ├── GET /api/offers?platform=Android&publisher=testerup&timestamp=...
    │       Reads the chosen .jsonl file
    │       Filters by targetDeviceType == "android"
    │       JS renders offer cards sorted by offerwall rank (sortOrder)
    │
    └── GET /api/offer-events?offer_id=67&targeting_id=...  (on card click)
            Makes live GraphQL call to TesterUP
            Merges goals + targetings → sorted event list with USD payouts
            JS renders event breakdown table in a modal
```

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| JSONL format (one JSON per line) | Easy to append, easy to read line-by-line, works with large files |
| Timestamped filenames | Preserves history; dashboard can compare any two dates |
| Both platforms in same API call | TesterUP's API returns all platforms at once; we save to the right folder and filter in /api/offers |
| Cached auth session in app.py | TesterUP's auth flow takes ~1s; caching means event breakdowns open instantly |
| `os.path.abspath(__file__)` for paths | Makes scripts work from any directory, not just when run from the project root |
| Skip 0-byte files | Failed crawl runs create empty files; we skip them so the dashboard never shows "No offers found" for a legitimate date |
| `targeting_id or None` in app.py | Converts empty string to null in GraphQL; avoids "no events found" bug for old JSONL files that didn't store targetingId |

---

## Extending the System

### Adding a new publisher

1. Create `{publisher}_crawler.py` that extends `BaseCrawler`
2. Implement `authenticate()` and `fetch_offers()` → yield `Offer` objects
3. Add a `run_{publisher}(output_file)` function in `run.py`
4. Add it to the `PUBLISHERS` dict in `run.py`
5. The dashboard will automatically show it in the Publisher dropdown

### Adding a new dashboard feature

- All UI logic is in `templates/index.html` (vanilla JS, no build step)
- API data is served from `app.py` — add new routes there for new data sources
- The `/api/offers` response includes the full `raw` field with the original TesterUP
  API response, so new fields can be displayed without re-crawling

---

## Security Notes

| Item | Approach |
|---|---|
| Credentials | Stored in `.env` only, never in code. `.env` is in `.gitignore`. |
| Access control | Dashboard binds to `127.0.0.1` only — not reachable from other machines |
| Debug mode | `debug=False` — Flask never exposes stack traces in the browser |
| Dependencies | Pinned in `requirements.txt` — use `pip install -r requirements.txt` for reproducible installs |
| CSRF | Not needed — the server only serves GET/static content; no user-submitted actions |
