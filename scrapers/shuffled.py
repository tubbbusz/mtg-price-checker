import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


def scrape_shuffled(card_name: str):
    url = f"https://shuffled.com.au/search?page=1&q=%2A{quote_plus(card_name)}%2A"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        target = card_name.strip().lower()
        results = []

        for card in soup.select("div.productCard__card"):
            title_tag = card.select_one("p.productCard__title a")
            if not title_tag:
                continue

            full_title = title_tag.get_text(strip=True)
            card_title = re.split(r"[\(\-]", full_title)[0].strip().lower()
            if card_title != target:
                continue

            href = title_tag.get("href", "").split("?")[0]
            link = "https://shuffled.com.au" + href if href.startswith("/") else href

            best_price = None
            for chip in card.select("li.productChip"):
                available = chip.get("data-variantavailable", "false") == "true"
                qty = int(chip.get("data-variantqty", "0") or 0)
                if not available or qty <= 0:
                    continue
                try:
                    price_cents = int(chip.get("data-variantprice", "0") or 0)
                    price = price_cents / 100
                except (ValueError, TypeError):
                    continue
                if price > 0 and (best_price is None or price < best_price):
                    best_price = price

            if best_price is not None:
                results.append((best_price, full_title, link))

        if not results:
            return (0.0, "Out of stock", "")
        return min(results, key=lambda x: x[0])
    except Exception:
        return (0.0, "Error", "")
