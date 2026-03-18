import gzip
import json
import requests
import threading
import traceback

_last_error = ""


def load_ck_prices() -> dict:
    """
    Load CK retail prices from MTGJSON.
    Uses AllPricesToday (today only = small file) keyed by UUID,
    and AtomicCards (name-keyed) to build the UUID->name mapping.
    Falls back cleanly if anything fails.
    """
    global _last_error

    headers = {"User-Agent": "ScrappingMyAss/1.0"}

    try:
        # Step 1: AtomicCards.json.gz — name-keyed, contains mtgjsonId per printing
        # This lets us build name -> set of UUIDs
        print("[CK] Downloading AtomicCards...")
        r1 = requests.get(
            "https://mtgjson.com/api/v5/AtomicCards.json.gz",
            headers=headers, timeout=60, stream=True,
        )
        r1.raise_for_status()
        atomic = json.loads(gzip.decompress(r1.content)).get("data", {})
        print(f"[CK] AtomicCards loaded: {len(atomic)} cards")

        # Build uuid -> canonical name map
        uuid_to_name = {}
        for name, printings in atomic.items():
            # printings is a list of card face objects
            for face in (printings if isinstance(printings, list) else [printings]):
                uid = face.get("identifiers", {}).get("mtgjsonId")
                if uid:
                    uuid_to_name[uid] = name

        print(f"[CK] UUID map: {len(uuid_to_name)} entries")

        # Step 2: AllPricesToday.json.gz — UUID-keyed, today only (small)
        print("[CK] Downloading AllPricesToday...")
        r2 = requests.get(
            "https://mtgjson.com/api/v5/AllPricesToday.json.gz",
            headers=headers, timeout=60, stream=True,
        )
        r2.raise_for_status()
        prices_data = json.loads(gzip.decompress(r2.content)).get("data", {})
        print(f"[CK] AllPricesToday loaded: {len(prices_data)} UUIDs")

        # Step 3: Build name -> cheapest CK retail USD
        cache = {}
        for uuid, price_block in prices_data.items():
            name = uuid_to_name.get(uuid, "").strip().lower()
            if not name:
                continue
            try:
                ck_retail = (
                    price_block.get("paper", {})
                    .get("cardkingdom", {})
                    .get("retail", {})
                    .get("normal", {})
                )
                if not ck_retail:
                    continue
                # dict of {date: price} — grab latest value
                price = float(list(ck_retail.values())[-1])
            except (TypeError, ValueError, AttributeError, IndexError):
                continue
            if price <= 0:
                continue
            if name not in cache or price < cache[name]:
                cache[name] = price

        _last_error = ""
        print(f"[CK] Built price cache: {len(cache)} cards")
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
