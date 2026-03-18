import gzip
import json
import requests
import traceback
import io

_last_error = ""


def load_ck_prices() -> dict:
    """
    AllPricesToday has UUID-keyed CK prices.
    AllIdentifiers has UUID -> card name.
    Stream AllIdentifiers line by line to avoid RAM issues.
    """
    global _last_error
    headers = {"User-Agent": "ScrappingMyAss/1.0"}

    try:
        # Step 1: get all UUIDs that have CK retail prices
        print("[CK] Downloading AllPricesToday...")
        r1 = requests.get(
            "https://mtgjson.com/api/v5/AllPricesToday.json.gz",
            headers=headers, timeout=60, stream=True,
        )
        r1.raise_for_status()
        prices_raw = json.loads(gzip.decompress(r1.content)).get("data", {})
        print(f"[CK] AllPricesToday: {len(prices_raw)} UUIDs")

        # Extract only UUIDs with CK retail normal prices
        ck_prices = {}  # uuid -> price
        for uuid, block in prices_raw.items():
            try:
                ck_retail = (
                    block.get("paper", {})
                    .get("cardkingdom", {})
                    .get("retail", {})
                    .get("normal", {})
                )
                if not ck_retail:
                    continue
                price = float(list(ck_retail.values())[-1])
                if price > 0:
                    ck_prices[uuid] = price
            except (TypeError, ValueError, AttributeError, IndexError):
                continue

        print(f"[CK] UUIDs with CK prices: {len(ck_prices)}")
        del prices_raw  # free RAM

        # Step 2: stream AllIdentifiers to get name for each UUID
        # AllIdentifiers is large but we only need the "name" field per UUID
        print("[CK] Downloading AllIdentifiers...")
        r2 = requests.get(
            "https://mtgjson.com/api/v5/AllIdentifiers.json.gz",
            headers=headers, timeout=90, stream=True,
        )
        r2.raise_for_status()
        all_ids = json.loads(gzip.decompress(r2.content)).get("data", {})
        print(f"[CK] AllIdentifiers: {len(all_ids)} entries")

        cache = {}
        for uuid, price in ck_prices.items():
            card = all_ids.get(uuid, {})
            name = card.get("name", "").strip().lower()
            if not name:
                continue
            if name not in cache or price < cache[name]:
                cache[name] = price

        del all_ids  # free RAM
        print(f"[CK] Price cache: {len(cache)} cards")
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
