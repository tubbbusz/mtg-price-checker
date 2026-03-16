import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


def scrape_jenes(card_name: str):
    url = f"https://jenesmtg.com.au/search?q={quote_plus(card_name)}&options%5Bprefix%5D=last"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        target = card_name.strip().lower()
        results = []

        for card in soup.select("div.mtg-card"):
            stock_badge = card.select_one("span.mtg-stock-badge")
            if not stock_badge or "in-stock" not in stock_badge.get("class", []):
                continue

            name_tag = card.select_one("a.mtg-card-name")
            if not name_tag:
                continue

            title_attr = name_tag.get("title", "")
            card_title = title_attr.split("|")[0].strip() if title_attr else name_tag.get_text(strip=True)
            if card_title.lower() != target:
                continue

            link = name_tag.get("href", "").split("?")[0]
            if link and not link.startswith("http"):
                link = "https://jenesmtg.com.au" + link

            price_tag = card.select_one("span.mtg-card-price")
            if not price_tag:
                continue
            match = re.search(r"\$([0-9]+\.[0-9]{2})", price_tag.get_text(strip=True))
            if not match:
                continue

            price = float(match.group(1))
            label = title_attr if title_attr else card_title
            results.append((price, label, link))

        if not results:
            return (0.0, "Out of stock", "")
        return min(results, key=lambda x: x[0])
    except Exception as e:
        return (0.0, "Error", "")
