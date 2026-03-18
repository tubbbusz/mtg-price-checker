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
from scrapers.cardkingdom import get_ck_price, load_ck_prices, get_last_error as ck_last_error

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
    from scrapers.utils import parse_card_query
    card_name, set_code, number, foil, etched = parse_card_query(card)

    futures = {}
    with ThreadPoolExecutor(max_workers=len(enabled)) as ex:
        for name in enabled:
            fn = SCRAPERS.get(name)
            if not fn:
                continue
            if name == "Hareruya":
                futures[name] = ex.submit(fn, card_name, hareruya_lang)
            elif name == "MTGMate":
                futures[name] = ex.submit(fn, card_name,
                                          None, set_code, number,
                                          True if foil else (False if etched else None))
            else:
                futures[name] = ex.submit(fn, card_name)

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

    ck_usd = get_ck_price(card_name, _ck_cache)
    ck_ratio = round(cheapest_price / ck_usd, 4) if (ck_usd and cheapest_price > 0) else None

    return {
        "card": card,  # keep original query as display name
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
            await asyncio.sleep(5)  # rate limit: 5s between cards to avoid blocks

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/fetch-deck")
async def fetch_deck_url(url: str = Query(...), include_sideboard: bool = False, include_maybeboard: bool = False):
    import re
    import requests as req_lib

    archidekt_match = re.search(r"archidekt\.com/decks/(\d+)", url)
    if archidekt_match:
        deck_id = archidekt_match.group(1)
        try:
            loop = asyncio.get_event_loop()
            def _fetch():
                r = req_lib.get(
                    f"https://archidekt.com/api/decks/{deck_id}/",
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=15,
                )
                r.raise_for_status()
                return r.json()
            data = await loop.run_in_executor(None, _fetch)
            cards = []
            for card in data.get("cards", []):
                categories = [c.lower() for c in card.get("categories", [])]
                if "maybeboard" in categories and not include_maybeboard:
                    continue
                if "sideboard" in categories and not include_sideboard:
                    continue
                name = card.get("card", {}).get("oracleCard", {}).get("name", "")
                qty = card.get("quantity", 1)
                if name:
                    cards.append({"qty": qty, "name": name})
            return {"cards": cards}
        except Exception as e:
            return {"error": str(e)}

    try:
        import mtg_parser
        loop = asyncio.get_event_loop()
        session = req_lib.Session()
        cards = await loop.run_in_executor(None, lambda: list(mtg_parser.parse_deck(url, session)))
        filtered = []
        for c in cards:
            if "sideboard" in c.tags and not include_sideboard:
                continue
            if "maybeboard" in c.tags and not include_maybeboard:
                continue
            filtered.append({"qty": c.quantity, "name": c.name})
        return {"cards": filtered}
    except Exception as e:
        return {"error": str(e)}


@app.get("/ck-status")
def ck_status():
    return {"ready": _ck_ready.is_set(), "count": len(_ck_cache), "error": ck_last_error()}

@app.get("/ck-debug")
def ck_debug():
    """Hit this URL in your browser to see exactly what CK loading is doing."""
    import requests, gzip
    results = {}

    # Test 1: AtomicCards
    try:
        r = requests.get("https://mtgjson.com/api/v5/AtomicCards.json.gz",
            headers={"User-Agent": "ScrappingMyAss/1.0"}, timeout=30, stream=True)
        results["atomic_status"] = r.status_code
        results["atomic_size_kb"] = len(r.content) // 1024
        data = gzip.decompress(r.content)
        parsed = __import__("json").loads(data)
        results["atomic_cards"] = len(parsed.get("data", {}))
    except Exception as e:
        results["atomic_error"] = str(e)

    # Test 2: AllPricesToday
    try:
        r2 = requests.get("https://mtgjson.com/api/v5/AllPricesToday.json.gz",
            headers={"User-Agent": "ScrappingMyAss/1.0"}, timeout=30, stream=True)
        results["prices_status"] = r2.status_code
        results["prices_size_kb"] = len(r2.content) // 1024
        data2 = gzip.decompress(r2.content)
        parsed2 = __import__("json").loads(data2)
        uuids = parsed2.get("data", {})
        results["prices_uuids"] = len(uuids)
        # Sample: check if cardkingdom key exists
        sample = next(iter(uuids.values()), {})
        results["sample_has_ck"] = "cardkingdom" in sample.get("paper", {})
    except Exception as e:
        results["prices_error"] = str(e)

    results["cache_count"] = len(_ck_cache)
    results["cache_ready"] = _ck_ready.is_set()
    results["last_error"] = ck_last_error()
    return results
