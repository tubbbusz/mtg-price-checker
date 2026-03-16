import re
import requests
from bs4 import BeautifulSoup
from .utils import parse_card_query


def scrape_moonmtg(query: str):
    BASE_URL = "https://moonmtg.com/products/"
    card_name, set_code, number, foil, etched = parse_card_query(query)

    handle = card_name.lower()
    handle = re.sub(r"[''\":,?!()]", "", handle)
    handle = re.sub(r"[^a-z0-9\s-]", "", handle)
    handle = re.sub(r"\s+", "-", handle)
    handle = handle.strip("-")

    def normalize_variant_title(title: str) -> str:
        t = title.upper()
        t = re.sub(r"\[.*?\]", "", t)
        t = re.sub(r"\(.*?\)", "", t)
        return t.strip()

    try:
        r = requests.get(f"{BASE_URL}{handle}.json", timeout=15)
        if r.status_code != 200:
            return (0.0, "Not found", "")
        product = r.json().get("product", {})
    except Exception:
        return (0.0, "Not found", "")

    variants = product.get("variants", [])
    matches = []

    for v in variants:
        title = v.get("title", "").upper()
        normalized = normalize_variant_title(title)
        vid = v.get("id")
        try:
            price = float(v.get("price", 0))
        except Exception:
            price = 0.0
        if price <= 0:
            continue

        try:
            s = requests.get(f"{BASE_URL}{handle}?variant={vid}", timeout=15)
            if s.status_code != 200:
                continue
            soup = BeautifulSoup(s.text, "html.parser")
            inv = soup.find("p", class_="product__inventory")
            stock_status = inv.get_text(strip=True) if inv else "Unknown"
            if stock_status in ["Out of stock", "Unknown", "Stock info not found"]:
                continue
        except Exception:
            continue

        url = f"{BASE_URL}{handle}?variant={vid}"

        if set_code and number:
            if normalized.startswith(f"{set_code} {number}") or normalized.startswith(f"{set_code}-{number}"):
                if foil and "FOIL" not in title:
                    continue
                if etched and "ETCHED" not in title:
                    continue
                return (price, title, url)
        elif set_code and normalized.startswith(set_code):
            if foil and "FOIL" not in title:
                continue
            if etched and "ETCHED" not in title:
                continue
            matches.append((price, title, url))
        elif not set_code:
            matches.append((price, title, url))

    if matches:
        return min(matches, key=lambda x: x[0])
    return (0.0, "Not found", "")
