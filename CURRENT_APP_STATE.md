# Current App State

_Last updated: 2026-05-25_

## Crawlers

| Publisher   | Platforms              | Status                          | Notes |
|-------------|------------------------|---------------------------------|-------|
| TesterUp    | Android, iOS, Desktop  | ✅ Working                      | Requires US IP / VPN |
| Kashkick    | Android                | ✅ Working                      | Public API, requires US IP |
| Freecash    | Android, iOS, Desktop  | ✅ Working — 600+ offers         | Authenticated via `fc_access_token` JWT cookie; token in `.env`, expires 2026-08-21 |
| Swagbucks   | —                      | ❌ Disabled                     | Removed from CRAWLER_CLASSES; API endpoint unknown |

## Infrastructure

- **Local run:** `bash run_with_vpn.sh` (requires ExpressVPN installed)
- **Data storage:** Vercel Blob — files uploaded by `blob-upload.js` after each crawl
- **Blob folders uploaded:** `Android/`, `iOS/`, `Desktop/` only
- **Dashboard:** Flask app (`app.py`), served locally or via Vercel (`vercel.json`)
- **Offer events:** TesterUp only — live GraphQL lookup on card click

## Known gaps

- Freecash token renewal: `fc_access_token` expires every 90 days; grab a fresh one from DevTools → Application → Cookies → freecash.com
- Swagbucks: needs correct API endpoint before re-enabling
- `blob-upload.js` requires `npm install @vercel/blob` (no package.json yet)
