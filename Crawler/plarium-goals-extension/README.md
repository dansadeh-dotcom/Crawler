# Plarium Rocks – Goals to Google Sheet

A Chrome extension that adds a **"📊 Download to Google Sheet"** button to the
Subdivision Goals page on Plarium Rocks. One click extracts all goals (with KPIs
and Core Initiatives) and opens a pre-filled, formatted Google Sheet in a new tab.

No OAuth setup. No Google Cloud project. Uses your existing Google account.

---

## Setup (2 minutes, one-time)

1. Open Chrome → go to `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** → select this folder (`plarium-goals-extension/`)
4. Done ✅

---

## Usage

1. Navigate to the Subdivision Goals page on Plarium Rocks
2. A blue **"📊 Download to Google Sheet"** button appears next to the filters
3. Click it — the button shows progress as it reads each goal's panel
4. A new Google Sheet opens automatically in a new tab, already filled in

The sheet includes:

| Column | Content |
|--------|---------|
| # | Goal number |
| Goal Name | Full goal title |
| Due Date | Quarter (e.g. Q4 2026) |
| Status | Plan / Delayed / Done |
| KPIs / Expected Results | All KPI bullet points |
| Core Initiatives | All initiative bullet points |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Button doesn't appear | Hard-refresh the Plarium Rocks page (Cmd+Shift+R) |
| Sheet opens but is empty | The paste may have missed — click cell A1 and press Cmd+V manually |
| Goals show empty KPIs | The Plarium Rocks page structure may have changed — check the console for errors |

---

## Files

```
plarium-goals-extension/
├── manifest.json   # Extension config (no OAuth needed)
├── content.js      # Injected into Plarium Rocks: button + data extraction
├── background.js   # Opens sheets.new and injects paste script
└── README.md       # This file
```
