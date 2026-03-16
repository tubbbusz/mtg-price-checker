import re
import requests
from bs4 import BeautifulSoup
from .utils import normalize


def _scrape_shopify_store(card_name: str, base_url: str):
    target = normalize(card_name)
    url = f"{base_url}/search?type=product&options%5Bprefix%5D=last&q={card_name.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for card in soup.select("div.product-card-list2"):
            title_tag = card.select_one(".grid-view-item__title")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if normalize(title.split("(")[0].split("[")[0]) != target:
                continue

            link_tag = card.select_one("a[href]")
            link = link_tag["href"] if link_tag else ""
            if link and not link.startswith("http"):
                link = base_url + link

            if card.select_one(".outstock-overlay"):
                continue
            if "grid-view-item--sold-out" in " ".join(card.get("class", [])):
                continue

            options = card.select("select.product-form__variants option")
            if options:
                all_disabled = all(
                    opt.has_attr("disabled") or opt.get("data-available") == "0"
                    for opt in options
                )
                if all_disabled:
                    continue

            price_tag = card.select_one(".product-price__price")
            if not price_tag:
                continue
            price_match = re.search(r"\$([\d.,]+)", price_tag.get_text())
            if not price_match:
                continue
            price = float(price_match.group(1).replace(",", ""))
            results.append((price, title, link))

        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception:
        return 0.0, "Error", ""


def scrape_gamesportal(card_name: str):
    return _scrape_shopify_store(card_name, "https://gamesportal.com.au")


def scrape_cardhub(card_name: str):
    return _scrape_shopify_store(card_name, "https://thecardhubaustralia.com.au")
