import gzip
import json
import requests


def load_ck_prices() -> dict:
    """
    Fetch CK retail prices via MTGJSON AllPrices + AllIdentifiers CDN.
    Returns {card_name_lower: cheapest_non_foil_retail_usd}.
    MTGJSON is a public CDN that won't block cloud server IPs.
    """
    try:
        print("[CK] Downloading AllPrices from MTGJSON...")
        prices_r = requests.get(
            "https://mtgjson.com/api/v5/AllPrices.json.gz",
            headers={"User-Agent": "MTGPriceChecker/1.0"},
            timeout=120,
            stream=True,
        )
        prices_r.raise_for_status()
        prices_data = json.loads(gzip.decompress(prices_r.content)).get("data", {})

        print("[CK] Downloading AllIdentifiers from MTGJSON...")
        ids_r = requests.get(
            "https://mtgjson.com/api/v5/AllIdentifiers.json.gz",
            headers={"User-Agent": "MTGPriceChecker/1.0"},
            timeout=120,
            stream=True,
        )
        ids_r.raise_for_status()
        ids_data = json.loads(gzip.decompress(ids_r.content)).get("data", {})

        cache = {}
        for uuid, price_block in prices_data.items():
            card_info = ids_data.get(uuid, {})
            name = card_info.get("name", "").strip().lower()
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
                price = float(list(ck_retail.values())[-1])
            except (TypeError, ValueError, AttributeError, IndexError):
                continue
            if price <= 0:
                continue
            if name not in cache or price < cache[name]:
                cache[name] = price

        print(f"[CK] Loaded {len(cache)} prices from MTGJSON")
        return cache

    except Exception as e:
        print(f"[CK] Failed to load prices: {e}")
        return {}


def get_ck_price(card_name: str, cache: dict) -> float | None:
    return cache.get(card_name.strip().lower())
