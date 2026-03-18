import cloudscraper
import threading
import traceback

_scraper = None
_scraper_lock = threading.Lock()
_last_error = ""


def _get_scraper():
    global _scraper
    with _scraper_lock:
        if _scraper is None:
            _scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
    return _scraper


def load_ck_prices() -> dict:
    global _last_error
    try:
        print("[CK] Fetching pricelist via cloudscraper...")
        scraper = _get_scraper()
        r = scraper.get(
            "https://api.cardkingdom.com/api/v2/pricelist",
            timeout=45,
        )
        print(f"[CK] HTTP {r.status_code} | preview: {r.text[:200]}")
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

        _last_error = ""
        print(f"[CK] Loaded {len(cache)} prices")
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
