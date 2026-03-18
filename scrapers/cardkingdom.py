import gzip
import json
import requests
import traceback

_last_error = ""


def load_ck_prices() -> dict:
    global _last_error
    ua = {"User-Agent": "ScrappingMyAss/1.0"}

    try:
        # Scryfall oracle-cards: ~10MB download, has name + mtgjson_id per card
        print("[CK] Getting Scryfall bulk-data URL...")
        meta = requests.get(
            "https://api.scryfall.com/bulk-data/oracle-cards",
            headers=ua, timeout=15
        ).json()
        url = meta["download_uri"]
        print(f"[CK] Downloading Scryfall oracle cards from {url}...")

        sr = requests.get(url, headers=ua, timeout=90, stream=True)
        sr.raise_for_status()
        cards = json.loads(sr.content)
        print(f"[CK] Scryfall: {len(cards)} cards")

        # Build mtgjson_id -> card name map
        id_map = {}
        for c in cards:
            mid = c.get("mtgjson_id", "")
            if mid:
                id_map[mid] = c.get("name", "")
        del cards
        print(f"[CK] mtgjson_id map: {len(id_map)} entries")

        # AllPricesToday — UUID-keyed CK prices (~5MB gz)
        print("[CK] Downloading AllPricesToday...")
        r = requests.get(
            "https://mtgjson.com/api/v5/AllPricesToday.json.gz",
            headers=ua, timeout=60, stream=True
        )
        r.raise_for_status()
        prices = json.loads(gzip.decompress(r.content)).get("data", {})
        print(f"[CK] AllPricesToday: {len(prices)} UUIDs")

        cache = {}
        for uuid, block in prices.items():
            name = id_map.get(uuid, "").strip().lower()
            if not name:
                continue
            try:
                ck = (block.get("paper", {})
                          .get("cardkingdom", {})
                          .get("retail", {})
                          .get("normal", {}))
                if not ck:
                    continue
                price = float(list(ck.values())[-1])
                if price > 0:
                    if name not in cache or price < cache[name]:
                        cache[name] = price
            except (TypeError, ValueError, AttributeError, IndexError):
                continue

        del prices, id_map
        print(f"[CK] Cache built: {len(cache)} cards")
        _last_error = ""
        return cache

    except Exception as e:
        _last_error = f"{type(e).__name__}: {e}"
        print(f"[CK] Failed: {_last_error}")
        traceback.print_exc()
        return {}


def get_ck_price(card_name: str, cache: dict) -> float | None:
    return cache.get(card_name.strip().lower()) if cache else None


def get_last_error() -> str:
    return _last_error
