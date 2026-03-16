import requests


def load_ck_prices() -> dict:
    """Fetch Card Kingdom price list and return a {name_lower: cheapest_usd} dict."""
    try:
        r = requests.get(
            "https://api.cardkingdom.com/api/v2/pricelist",
            headers={"User-Agent": "MTGPriceChecker/1.0 (contact: kadenschaedel@gmail.com)"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        cache = {}
        for item in data.get("data", []):
            if str(item.get("is_foil", "0")) == "1":
                continue
            name = item.get("name", "").strip().lower()
            try:
                price = float(item.get("price_retail", 0) or 0)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            if name not in cache or price < cache[name]:
                cache[name] = price
        return cache
    except Exception as e:
        print(f"[CK] Failed to load price list: {e}")
        return {}


def get_ck_price(card_name: str, cache: dict) -> float | None:
    return cache.get(card_name.strip().lower())
