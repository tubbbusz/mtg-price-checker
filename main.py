import asyncio
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from scrapers.cardhub import scrape_cardhub
from scrapers.gamesportal import scrape_gamesportal
from scrapers.gg import scrape_ggadelaide, scrape_ggaustralia, scrape_ggmodbury
from scrapers.hareruya import scrape_hareruyamtg
from scrapers.jenes import scrape_jenes
from scrapers.kcg import scrape_kcg
from scrapers.moonmtg import scrape_moonmtg
from scrapers.mtgmate import fetch_mtgmate_price
from scrapers.shuffled import scrape_shuffled
from scrapers.cardkingdom import get_ck_price, load_ck_prices

app = FastAPI(title="MTG Price Checker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Card Kingdom price cache (loaded once at startup) ─────────────────────────
_ck_cache: dict = {}
_ck_ready = threading.Event()

def _init_ck():
    global _ck_cache
    _ck_cache = load_ck_prices()
    _ck_ready.set()

threading.Thread(target=_init_ck, daemon=True).start()

# ── Scraper registry ──────────────────────────────────────────────────────────
SCRAPERS = {
    "CardHub":     scrape_cardhub,
    "GamesPortal": scrape_gamesportal,
    "GGAdelaide":  scrape_ggadelaide,
    "GGAustralia": scrape_ggaustralia,
    "GGModbury":   scrape_ggmodbury,
    "Hareruya":    scrape_hareruyamtg,
    "JenesMTG":    scrape_jenes,
    "KCG":         scrape_kcg,
    "MoonMTG":     scrape_moonmtg,
    "MTGMate":     fetch_mtgmate_price,
    "Shuffled":    scrape_shuffled,
}

# ── Models ────────────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    cards: list[str]
    enabled_sources: list[str] = list(SCRAPERS.keys())
    hareruya_lang: str = "EN"


# ── Helpers ───────────────────────────────────────────────────────────────────
def fetch_card(card: str, enabled: list[str], hareruya_lang: str) -> dict:
    """Run all enabled scrapers for one card in parallel threads."""
    futures = {}
    with ThreadPoolExecutor(max_workers=len(enabled)) as ex:
        for name in enabled:
            fn = SCRAPERS.get(name)
            if not fn:
                continue
            if name == "Hareruya":
                futures[name] = ex.submit(fn, card, hareruya_lang)
            else:
                futures[name] = ex.submit(fn, card)

    results = {}
    for name, fut in futures.items():
        try:
            r = fut.result(timeout=30)
            if isinstance(r, tuple) and len(r) >= 3:
                results[name] = {"price": r[0], "label": r[1], "url": r[2]}
                if name == "Hareruya" and len(r) == 4:
                    results[name]["jpy"] = r[3]
            else:
                results[name] = {"price": 0.0, "label": "Error", "url": ""}
        except Exception as e:
            results[name] = {"price": 0.0, "label": f"Error: {e}", "url": ""}

    # Cheapest across enabled sources
    prices = [(n, d["price"]) for n, d in results.items() if d["price"] > 0]
    cheapest_price = min((p for _, p in prices), default=0.0)
    cheapest_source = next((n for n, p in prices if p == cheapest_price), "")
    cheapest_url = results.get(cheapest_source, {}).get("url", "") if cheapest_source else ""

    ck_usd = get_ck_price(card, _ck_cache)
    ck_ratio = round(ck_usd / cheapest_price, 4) if (ck_usd and cheapest_price > 0) else None

    return {
        "card": card,
        "results": results,
        "cheapest_price": cheapest_price,
        "cheapest_source": cheapest_source,
        "cheapest_url": cheapest_url,
        "ck_usd": ck_usd,
        "ck_ratio": ck_ratio,
    }


def parse_decklist(text: str) -> list[str]:
    import re
    cards = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"(\d+x?\s*)?(.*)", line, re.IGNORECASE)
        if m:
            name = m.group(2).strip()
            if name:
                cards.append(name)
    return cards


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html")) as f:
        return f.read()


@app.get("/sources")
def get_sources():
    return list(SCRAPERS.keys())


@app.post("/search/stream")
async def search_stream(req: SearchRequest):
    """
    Server-Sent Events stream.
    Yields one JSON line per card as soon as it completes.
    """
    loop = asyncio.get_event_loop()

    async def event_gen():
        # Yield a "start" event so the client knows total count
        yield f"data: {json.dumps({'type': 'start', 'total': len(req.cards)})}\n\n"

        for i, card in enumerate(req.cards, 1):
            result = await loop.run_in_executor(
                None, fetch_card, card, req.enabled_sources, req.hareruya_lang
            )
            payload = {"type": "result", "index": i, **result}
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0)  # yield control

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/fetch-deck")
async def fetch_deck_url(url: str = Query(...), include_sideboard: bool = False, include_maybeboard: bool = False):
    import re, requests

    # Archidekt — use their public API directly
    archidekt_match = re.search(r"archidekt\.com/decks/(\d+)", url)
    if archidekt_match:
        deck_id = archidekt_match.group(1)
        try:
            r = requests.get(
                f"https://archidekt.com/api/decks/{deck_id}/",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15
            )
            r.raise_for_status()
            data = r.json()
            cards = []
            for card in data.get("cards", []):
                categories = [c.get("name", "").lower() for c in card.get("categories", [])]
                if "sideboard" in categories and not include_sideboard:
                    continue
                if "maybeboard" in categories and not include_maybeboard:
                    continue
                name = card.get("card", {}).get("oracleCard", {}).get("name", "")
                qty = card.get("quantity", 1)
                if name:
                    cards.append({"qty": qty, "name": name})
            return {"cards": cards}
        except Exception as e:
            return {"error": str(e)}

    # Fallback — mtg_parser for other sites
    try:
        import mtg_parser, requests
        loop = asyncio.get_event_loop()
        session = requests.Session()
        cards = await loop.run_in_executor(None, lambda: list(mtg_parser.parse_deck(url, session)))
        filtered = [{"qty": c.quantity, "name": c.name} for c in cards
                    if not ("sideboard" in c.tags and not include_sideboard)
                    and not ("maybeboard" in c.tags and not include_maybeboard)]
        return {"cards": filtered}
    except Exception as e:
        return {"error": str(e)}

@app.get("/ck-status")
def ck_status():
    return {"ready": _ck_ready.is_set(), "count": len(_ck_cache)}
