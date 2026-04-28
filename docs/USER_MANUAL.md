# Offer Wall Dashboard — User Guide

**For:** Marketing team members who want to view and compare offer walls across publishers

> **You don't need to run the crawler.** The offer wall data is already collected daily and stored in the shared folder. You just need to do a one-time setup and then start a small local server each time you want to use the dashboard.

---

## What the dashboard lets you do

- **See any day's offer wall** — pick a date from the dropdown and see all active offers
- **Filter by platform** — switch between Android, iOS, and Desktop offer walls instantly
- **Check your ranking** — see where your game (e.g. Raid: Shadow Legends) appears on the wall. Rank #1 means a user sees it first
- **Compare two dates** — turn on Compare Mode to see two dates side by side
- **See per-event payouts** — click any offer card to see how much each in-game event pays out
- **Compare specific offers** — use the Compare Offers bar to select multiple games and view their event breakdowns side by side

---

## One-time setup

You only need to do this once on your computer. Follow the section for your operating system.

- [Setup for Mac](#one-time-setup-mac)
- [Setup for Windows](#one-time-setup-windows)

---

## One-time setup — Mac

### Step 1 — Install Python

Open Terminal (press ⌘+Space, type "Terminal", press Enter).

Check if Python is already installed:
```
python3 --version
```

If you see a version number (e.g. `Python 3.12.3`), skip to Step 2.

If you see an error, install Python from: **https://www.python.org/downloads/**
Download the latest version and run the installer.

---

### Step 2 — Make sure Google Drive is synced

The Crawler folder is shared via Google Drive. On your Mac, it should appear at:

```
~/Library/CloudStorage/GoogleDrive-[your-email]@plarium.com/My Drive/Crawler (1)
```

If the folder isn't there, make sure **Google Drive for Desktop** is installed and signed in with your Plarium account. Download from: https://www.google.com/drive/download/

---

### Step 3 — Set up the Python environment

In Terminal, run these commands **one at a time**. Replace `[your-email]` with your Plarium email prefix (e.g. `john.doe`).

**a) Go to the Crawler folder:**
```bash
cd ~/Library/CloudStorage/GoogleDrive-[your-email]@plarium.com/My\ Drive/Crawler\ \(1\)
```

**b) Create a Python environment:**
```bash
python3 -m venv venv
```

**c) Activate it:**
```bash
source venv/bin/activate
```
You'll see `(venv)` appear at the start of your terminal prompt — that's correct.

**d) Install the required packages:**
```bash
pip install -r requirements.txt
```
Wait for it to finish (about 30 seconds).

---

### Step 4 — Create your credentials file

In the Crawler folder, find the file called **`.env.example`** and make a copy named **`.env`**.

> **Note:** Files starting with `.` may be hidden in Finder. To show hidden files, press **⌘+Shift+.** (Command + Shift + Period) inside Finder.

Open `.env` in any text editor and fill in your TesterUP credentials:

```
TESTERUP_EMAIL=your@email.com
TESTERUP_PASSWORD=yourpassword
TESTERAPP_COUNTRY=US
```

Save the file.

---

## Opening the dashboard — Mac (every time you want to use it)

**Step 1 — Open Terminal** (⌘+Space → "Terminal" → Enter)

**Step 2 — Paste this command** (replace `[your-email]`) **and press Enter:**
```bash
cd ~/Library/CloudStorage/GoogleDrive-[your-email]@plarium.com/My\ Drive/Crawler\ \(1\) && source venv/bin/activate && python app.py
```

You should see:
```
✅  Dashboard running at http://localhost:5000
```

**Step 3 — Open your browser** and go to:
```
http://localhost:5000
```

**Step 4 — When you're done**, go back to Terminal and press **Ctrl+C** to stop the server.

---

## One-time setup — Windows

### Step 1 — Install Python

Open **PowerShell** (press the Windows key, type "PowerShell", press Enter).

Check if Python is already installed:
```
python --version
```

If you see a version number (e.g. `Python 3.12.3`), skip to Step 2.

If you see an error, install Python from: **https://www.python.org/downloads/**
Download the latest version, run the installer, and **make sure to tick "Add Python to PATH"** before clicking Install.

---

### Step 2 — Find the Google Drive folder

The Crawler folder is shared via Google Drive. On Windows, Google Drive appears as a drive in File Explorer (usually `G:` or `H:`).

Open **File Explorer** and look for **Google Drive** in the left panel. Click it, then navigate to **My Drive → Crawler (1)**.

Note the full path shown at the top of File Explorer — it will look something like:
```
G:\My Drive\Crawler (1)
```

---

### Step 3 — Allow PowerShell scripts to run (one-time)

PowerShell blocks scripts by default. Run this command once to allow them:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Type `Y` and press Enter if prompted.

---

### Step 4 — Set up the Python environment

In PowerShell, run these commands **one at a time**. Replace `G:` with your actual Google Drive letter if different.

**a) Go to the Crawler folder:**
```powershell
cd "G:\My Drive\Crawler (1)"
```

**b) Create a Python environment:**
```powershell
python -m venv venv
```

**c) Activate it:**
```powershell
.\venv\Scripts\Activate.ps1
```
You'll see `(venv)` appear at the start of your prompt — that's correct.

**d) Install the required packages:**
```powershell
pip install -r requirements.txt
```
Wait for it to finish (about 30 seconds).

---

### Step 5 — Create your credentials file

In the Crawler folder, find the file called **`.env.example`** and make a copy named **`.env`**.

> **Note:** Files starting with `.` may be hidden. In File Explorer, go to **View → Show → Hidden items** to make them visible.

Open `.env` in any text editor (Notepad, VS Code, etc.) and fill in your TesterUP credentials:

```
TESTERUP_EMAIL=your@email.com
TESTERUP_PASSWORD=yourpassword
TESTERAPP_COUNTRY=US
```

Save the file.

---

## Opening the dashboard — Windows (every time you want to use it)

**Step 1 — Open PowerShell** (Windows key → type "PowerShell" → Enter)

**Step 2 — Run these three commands one at a time** (replace `G:` with your Google Drive letter):

```powershell
cd "G:\My Drive\Crawler (1)"
```
```powershell
.\venv\Scripts\Activate.ps1
```
```powershell
python app.py
```

You should see:
```
✅  Dashboard running at http://localhost:5000
```

**Step 3 — Open your browser** and go to:
```
http://localhost:5000
```

**Step 4 — When you're done**, go back to PowerShell and press **Ctrl+C** to stop the server.

---

## Using the dashboard

### Reading the offer wall

When the page loads, it automatically shows:
- **Publisher:** TesterUP
- **Platform:** Android
- **Date:** Yesterday's crawl (most recent available)

> **Note:** Not all publishers support all platforms. Kashkick is Android-only. TesterUP supports Android, iOS, and Desktop.

Each card shows one game/app on the offer wall with:
- 🥇 **Rank badge** — the position on the offer wall (Rank 1 = first offer a user sees)
- **Game icon and name**
- **Total payout** in USD
- **Category** (Mobile Game, etc.)

Cards are sorted by rank by default (rank 1 first).

---

### Changing what you see

Use the dropdowns at the top:

| Dropdown | What it does |
|---|---|
| **Publisher** | Choose which ad network's offer wall to view (see supported publishers below) |
| **Platform** | Switch between Android, iOS, and Desktop offer walls |
| **Date** | Pick any date that has been crawled |

---

### Supported publishers & platforms

| Publisher | Android | iOS | Desktop |
|---|---|---|---|
| **TesterUP** | ✅ | ✅ | ✅ |
| **Kashkick** | ✅ | ❌ Android-only | ❌ Android-only |
| **Freecash** | 🔜 Coming soon | 🔜 Coming soon | 🔜 Coming soon |
| **Swagbucks** | 🔜 Coming soon | 🔜 Coming soon | 🔜 Coming soon |

The cards update instantly when you change a dropdown.

---

### Sorting offers

Use the sort buttons above the cards:

| Sort option | What it shows |
|---|---|
| **Rank** (default) | Offerwall position — Rank 1 = most prominent placement |
| **Payout ↓** | Highest paying offers first |
| **Payout ↑** | Lowest paying offers first |
| **A → Z** | Alphabetical by game name |

---

### Seeing per-event payouts

Click on any offer card to open a detail panel showing:
- Each in-game event (e.g. "Complete Tutorial", "Reach Level 30")
- The USD payout for completing that event
- Time limits if applicable

This data is fetched live from TesterUP when you click.

---

### Comparing two dates

1. Toggle the **Compare Mode** switch at the top right
2. A second panel appears on the right with its own dropdowns
3. Pick a different date (or different platform/publisher) in the right panel
4. Both offer walls are shown side by side

This is useful for answering questions like:
- "Did our ranking improve between yesterday and last week?"
- "Are the payouts different on iOS vs Android vs Desktop?"

---

### Comparing specific offers

Use the **Compare Offers** bar below the main controls:

1. Type a game name in the search box (e.g. "Raid")
2. Select it from the dropdown — a chip (tag) appears
3. Add more offers if you want
4. Click **Compare** to see all selected offers' event breakdowns side by side

This is useful for:
- Comparing your game's events vs a competitor's
- Seeing which offer has the most/fewest steps to earn the reward

---

## Troubleshooting

**"No offers found" on a date**
The crawl for that date may have failed. Try a different date. The daily crawl runs at 7 AM automatically.

**The page won't load at http://localhost:5000**
Make sure you ran all three commands. Check the terminal — if you see `✅ Dashboard running`, the server is up.

**PowerShell says "running scripts is disabled"**
Run this once: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` and try again.

**Per-event breakdown shows an error**
Your `.env` file may be missing or have incorrect credentials. Check that you completed the credentials step in the one-time setup.

**The Crawler folder doesn't appear in File Explorer / Finder**
Make sure Google Drive for Desktop is installed and signed in with your Plarium account. Download from: https://www.google.com/drive/download/

---

## Keyboard shortcut

Press **Escape** to close any open offer detail or comparison panel.

---

## Questions?

Contact Michal Lichtman (michal.lichtman@plarium.com).
