# Errors Log

## TesterUp / Kashkick — 0 offers or 403 when running without VPN

**Symptom:** TesterUp returns `success: true` with empty offers array; Kashkick returns HTTP 403.
**Root cause:** Both publishers geo-restrict to US IPs. Running from IL returns no data.
**Fix:** Always use `bash run_with_vpn.sh`, never `python run.py` directly.

## TesterUp offer-events — silent failure (fixed 2026-05-25)

**Symptom:** Clicking any offer in dashboard showed "No event breakdown available" with no error.
**Root cause:** `app.py` `_get_session()` called `/api/auth/csrf` which returns 403. Token was never obtained.
**Fix:** Replaced with homepage-CSRF flow (same as `testerup_crawler.py`). Added 50-min TTL.
