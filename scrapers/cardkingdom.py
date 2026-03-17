import cloudscraper
import threading

_scraper = None
_scraper_lock = threading.Lock()

def _get_scraper():
    global _scraper
    with _scraper_lock:
        if _scraper is None:
            _scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
    return _scraper


def load_ck_prices() -> dict:
    """
    Fetch CK retail prices using cloudscraper to bypass Cloudflare.
    Returns {card_name_lower: cheapest_non_foil_retail_usd}.
    """
    try:
        print("[CK] Fetching pricelist via cloudscraper...")
        scraper = _get_scraper()
        r = scraper.get(
            "https://api.cardkingdom.com/api/v2/pricelist",
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

        print(f"[CK] Loaded {len(cache)} prices")
        return cache

    except Exception as e:
        print(f"[CK] Failed: {e}")
        return {}


def get_ck_price(card_name: str, cache: dict) -> float | None:
    return cache.get(card_name.strip().lower()) if cache else None
