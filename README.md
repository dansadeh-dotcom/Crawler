# TesterUP Offer Wall Crawler & Dashboard

A tool that automatically pulls the TesterUP offer wall every day and lets you
view, filter, and compare offers across dates and platforms through a browser-based dashboard.

---

## What it does

- **Crawls** TesterUP's offer wall for both Android and iOS daily at 7 AM
- **Saves** results as timestamped JSONL files so you can compare any two dates
- **Shows** a visual dashboard with offer cards, filters, rank badges, and compare mode
- **Breaks down** each offer's per-event payouts when you click on a card

---

## Quick start

### For dashboard users (marketing team)
See **[docs/USER_MANUAL.md](docs/USER_MANUAL.md)** — step-by-step guide for non-technical users.

### For developers
See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — system design, data flow, and extension guide.

---

## Project location

```
Google Drive / My Drive / Crawler/
```

Local path on Mac:
```
~/Library/CloudStorage/GoogleDrive-michal.lichtman@plarium.com/My Drive/Crawler/
```

---

## Folder structure

```
Crawler/
├── .env                    ← your credentials (copy from .env.example to create)
├── .env.example            ← credentials template — fill in and rename to .env
├── .gitignore              ← keeps credentials and machine-specific files out of git
├── requirements.txt        ← exact Python dependency versions for reproducible installs
│
├── run.py                  ← CRAWLER — run this to fetch a fresh offer wall snapshot
├── testerup_crawler.py     ← handles login and GraphQL API calls to TesterUP
├── base_crawler.py         ← shared Offer data model and BaseCrawler interface
│
├── app.py                  ← DASHBOARD server — run this to open the visual UI
├── templates/
│   └── index.html          ← single-page dashboard (HTML + CSS + vanilla JS)
│
├── Android/                ← Android crawl results (auto-created by run.py)
│   └── testerup_offers_YYYYMMDD_HHMMSS.jsonl
├── iOS/                    ← iOS crawl results (auto-created by run.py)
│   └── testerup_offers_YYYYMMDD_HHMMSS.jsonl
│
├── venv/                   ← Python virtual environment (do not share / do not commit)
│
└── docs/
    ├── ARCHITECTURE.md     ← system design, data flow diagrams, extension guide
    └── USER_MANUAL.md      ← non-technical guide for dashboard users
```

---

## One-time setup

```bash
# 1. Go to the project folder
cd ~/Library/CloudStorage/GoogleDrive-michal.lichtman@plarium.com/My\ Drive/Crawler

# 2. Create Python virtual environment
python3 -m venv venv

# 3. Activate it
source venv/bin/activate

# 4. Install all dependencies (exact versions pinned in requirements.txt)
pip install -r requirements.txt

# 5. Create your credentials file
cp .env.example .env
# Then open .env and fill in your TesterUP email and password
```

---

## Running the crawler

Fetches the current offer wall and saves new timestamped files for both platforms.

```bash
cd ~/Library/CloudStorage/GoogleDrive-michal.lichtman@plarium.com/My\ Drive/Crawler && source venv/bin/activate && python run.py
```

The crawler also runs **automatically every day at 7:00 AM** via the scheduled task.

---

## Opening the dashboard

```bash
cd ~/Library/CloudStorage/GoogleDrive-michal.lichtman@plarium.com/My\ Drive/Crawler && source venv/bin/activate && python app.py
```

Then open **[http://localhost:5000](http://localhost:5000)** in your browser.

### Dashboard features

| Feature | How to use |
|---|---|
| View offers | Select publisher, platform, and date from the dropdowns |
| Check offerwall ranking | Cards show rank badges; sort by Rank to see position 1 first |
| Compare two dates | Toggle **Compare Mode** to show two panels side by side |
| See event breakdown | Click any offer card |
| Compare specific offers | Use the **Compare Offers** search bar to select multiple offers |

---

## Credentials

Stored in `.env` — never hard-coded in Python files.

```
TESTERUP_EMAIL=your@email.com
TESTERUP_PASSWORD=yourpassword
TESTERAPP_COUNTRY=US
```

Each user needs their own `.env`. Copy `.env.example`, rename to `.env`, fill in.

---

## Result file format

Each `.jsonl` file contains one JSON object per line:

```json
{
  "publisher": "testerup",
  "offer_id": "67",
  "title": "RAID: Shadow Legends",
  "payout": 67.0,
  "currency": "USD",
  "category": "Mobile Game",
  "platform": "android",
  "icon_url": "https://...",
  "status": "active",
  "crawled_at": "2026-03-21T15:47:01",
  "raw": { "...original TesterUP API response..." }
}
```

---

## Adding more publishers

1. Create `{publisher}_crawler.py` extending `BaseCrawler` (see `base_crawler.py`)
2. Implement `authenticate()` and `fetch_offers()`
3. Add a `run_{publisher}(output_file)` function in `run.py`
4. Add it to the `PUBLISHERS` dict in `run.py`
5. It will appear automatically in the dashboard Publisher dropdown

---

## Security

| Item | Approach |
|---|---|
| Credentials | `.env` file only — not in code, not committed |
| Server access | Binds to `127.0.0.1` (localhost only) |
| Debug mode | `False` — no stack traces exposed in browser |
| Dependencies | Pinned in `requirements.txt` |
