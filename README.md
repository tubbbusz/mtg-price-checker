# MTG Price Checker — Web Edition

A web-based MTG card price comparison tool that scrapes 11 Australian/Japanese
stores in parallel and displays live results as they come in.

---

## Project Structure

```
mtg-web/
├── main.py                  # FastAPI app + API routes
├── requirements.txt
├── Procfile                 # Railway start command
├── railway.json             # Railway config
├── static/
│   └── index.html           # Full frontend (single file)
└── scrapers/
    ├── __init__.py
    ├── utils.py             # Shared normalisation helpers
    ├── cardkingdom.py       # CK price list cache
    ├── cardhub.py
    ├── gamesportal.py       # Also contains scrape_cardhub
    ├── gg.py                # GGAdelaide, GGModbury, GGAustralia
    ├── hareruya.py
    ├── jenes.py
    ├── kcg.py
    ├── moonmtg.py
    ├── mtgmate.py
    └── shuffled.py
```

---

## Local Development

### 1. Install dependencies

```bash
cd mtg-web
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Run the server

```bash
uvicorn main:app --reload --port 8000
```

Then open **http://localhost:8000** in your browser.

---

## Deploy to Railway (Free Hosting)

Railway gives you ~500 free hours/month — more than enough for a small group.

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "initial commit"
# Create a new repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/mtg-price-checker.git
git push -u origin main
```

### Step 2 — Create Railway project

1. Go to **https://railway.app** and sign in with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Select your `mtg-price-checker` repo
4. Railway auto-detects the Procfile and starts the build

### Step 3 — Get your URL

Once deployed (usually ~2 min):
1. Click your service in Railway dashboard
2. Go to **Settings → Networking → Generate Domain**
3. You'll get a URL like `https://mtg-price-checker-production.up.railway.app`

Share that URL with your group — no login required.

### Step 4 — Auto-deploys

Every `git push` to `main` will automatically redeploy. Takes ~90 seconds.

---

## Usage

1. **Paste a decklist** in the text area, or **paste a deck URL** (Archidekt,
   EDHREC, etc.) and click Fetch
2. Click **▶ Search Prices** — results stream in card by card
3. **Click a row once** to select it; **click again** to open the cheapest link
4. **Right-click** any row to open from a specific source
5. **CK% column**: green = cheaper than Card Kingdom USD price, red = more expensive
6. **Export CSV** saves all prices locally

### Source Toggles

Disable sources you don't care about — the Cheapest column and total
recalculate instantly without re-searching.

### Hareruya Language

- `EN` — English cards only (default)
- `EN→JP` — English first, falls back to Japanese if EN is out of stock
- `JP` — Japanese only
- `All` — all languages

---

## Updating the JPY→AUD Rate

In `scrapers/hareruya.py`, line 7:

```python
JPY_TO_AUD = 1 / 113.49   # update this periodically
```

---

## Notes

- **Rate limiting**: searches run with a 3-second gap between cards to avoid
  getting blocked. A 60-card deck takes ~3 minutes.
- **Card Kingdom prices** are fetched once at startup from their public API
  and cached in memory for the session.
- **Playwright** is imported in the original script but not actually used by
  any scraper — it has been omitted from this version.
- The app has **no authentication** — anyone with the URL can use it.
  Railway's free tier URL is not publicly indexed, so it's effectively
  private-by-obscurity for a small group.
