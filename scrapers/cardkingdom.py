import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

_last_error = ""


def load_ck_prices() -> dict:
    """CK prices are now fetched per-card at search time."""
    print("[CK] Per-card scraping mode — no bulk load needed")
    return {"_ready": True}  # non-empty so badge shows ready


def get_ck_price(card_name: str, cache: dict) -> float | None:
    """Scrape CK search page for cheapest NM in-stock price."""
    global _last_error
    try:
        url = (
            f"https://www.cardkingdom.com/catalog/view"
            f"?filter[search]=mtg_advanced&filter[name]={quote_plus(card_name)}"
        )
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        best = None
        for item in soup.select("div.productItemWrapper"):
            # Get card name from the title link
            title_tag = item.select_one("span.productDetailTitle a")
            if not title_tag:
                continue
            item_name = title_tag.get_text(strip=True).lower()
            if item_name != card_name.strip().lower():
                continue

            # Find NM add-to-cart form — must be active (in stock)
            for li in item.select("li.itemAddToCart.NM"):
                # Skip if out of stock
                if li.select_one("div.outOfStockNotice"):
                    continue
                price_tag = li.select_one("span.stylePrice")
                if not price_tag:
                    continue
                m = re.search(r"\$([\d.]+)", price_tag.get_text())
                if not m:
                    continue
                price = float(m.group(1))
                if price > 0 and (best is None or price < best):
                    best = price

        _last_error = ""
        return best

    except Exception as e:
        _last_error = str(e)
        return None


def get_last_error() -> str:
    return _last_error
