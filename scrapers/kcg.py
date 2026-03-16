import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


def scrape_kcg(card_name: str):
    url = f"https://kastlecardsandgames.com/search?type=product&q={quote_plus(card_name)}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        target = card_name.strip().lower()
        results = []

        for card in soup.select("product-card"):
            title_tag = card.select_one("a.product-card__link span.visually-hidden") or card.select_one("h3")
            if not title_tag:
                continue

            full_title = title_tag.get_text(strip=True)
            card_title = re.split(r"\[", full_title)[0].strip().lower()
            if card_title != target:
                continue

            sold_out_badge = card.select_one("div.product-badges__badge")
            if sold_out_badge and "Sold out" in sold_out_badge.get_text():
                continue

            add_btn = card.select_one("button.quick-add__button--add")
            if add_btn and add_btn.has_attr("disabled"):
                continue

            link_tag = card.select_one("a.product-card__link")
            href = link_tag.get("href", "").split("?")[0] if link_tag else ""
            link = "https://kastlecardsandgames.com" + href if href.startswith("/") else href

            price_tag = card.select_one("span.price")
            if not price_tag:
                continue
            price_text = price_tag.get_text(strip=True)
            match = re.search(r"\$([0-9]+\.[0-9]{2})", price_text)
            if not match:
                continue

            price = float(match.group(1))
            results.append((price, full_title, link))

        if not results:
            return (0.0, "Out of stock", "")
        return min(results, key=lambda x: x[0])
    except Exception:
        return (0.0, "Error", "")
