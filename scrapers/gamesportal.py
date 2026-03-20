import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from .gg import _extract_base_name, _get_set_from_title, _is_foil_title
from .setnames import get_set_name


def _scrape_shopify(card_name, base_url, set_code=None, number=None, foil=None):
    target = _extract_base_name(card_name)
    target_set_name = get_set_name(set_code).lower() if set_code else None
    query = quote_plus(card_name)
    url = f"{base_url}/search?type=product&options%5Bprefix%5D=last&q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []

        for card in soup.select("div.product-card-list2"):
            title_tag = card.select_one(".grid-view-item__title")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if _extract_base_name(title) != target:
                continue

            if card.select_one(".outstock-overlay"):
                continue
            if "grid-view-item--sold-out" in " ".join(card.get("class", [])):
                continue

            # Foil from title
            title_is_foil = _is_foil_title(title)
            if foil is True and not title_is_foil:
                continue
            if foil is False and title_is_foil:
                continue

            # Set from title brackets
            title_set = _get_set_from_title(title).lower()
            if target_set_name and target_set_name not in title_set and title_set not in target_set_name:
                continue

            link_tag = card.select_one("a[href]")
            link = link_tag["href"] if link_tag else ""
            if link and not link.startswith("http"):
                link = base_url + link

            price_tag = card.select_one(".product-price__price")
            if not price_tag:
                continue
            pm = re.search(r"\$([\d.,]+)", price_tag.get_text())
            if not pm:
                continue
            price = float(pm.group(1).replace(",", ""))
            results.append((price, title, link))

        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception as e:
        return 0.0, "Error", ""


def scrape_gamesportal(card_name: str, set_code=None, number=None, foil=None):
    return _scrape_shopify(card_name, "https://gamesportal.com.au", set_code, number, foil)


def scrape_cardhub(card_name: str, set_code=None, number=None, foil=None):
    return _scrape_shopify(card_name, "https://thecardhubaustralia.com.au", set_code, number, foil)
