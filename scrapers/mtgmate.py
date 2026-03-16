import re
import json
import cloudscraper
from bs4 import BeautifulSoup
from .utils import normalize


def fetch_mtgmate_price(card_name: str, set_name: str = None, set_code: str = None,
                        number: str = None, foil: bool = None):
    url = f"https://www.mtgmate.com.au/cards/search?q={card_name.replace(' ', '+')}"
    scraper = cloudscraper.create_scraper()

    try:
        r = scraper.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        return (0.0, "Error", "")

    soup = BeautifulSoup(r.text, "html.parser")
    container = soup.find("div", {"data-react-class": "FilterableTable"})
    if not container:
        return (0.0, "Not found", "")

    raw_props = container.get("data-react-props")
    if not raw_props:
        return (0.0, "Not found", "")

    try:
        data = json.loads(raw_props)
    except Exception:
        return (0.0, "Error", "")

    uuid_map = data.get("uuid", {})
    results = []
    target_norm = normalize(card_name)

    for card in data.get("cards", []):
        card_id = card.get("uuid")
        details = uuid_map.get(card_id, {})
        if not details:
            continue

        product_name = details.get("name", "")
        if normalize(product_name) != target_norm:
            continue

        try:
            price = int(details.get("price", 0)) / 100
        except Exception:
            price = 0.0

        qty = details.get("quantity", 0)
        if price <= 0 or qty <= 0:
            continue

        link_path = details.get("link_path", "")
        match = re.search(r"/([A-Z0-9]+)/(\d+):?", link_path)
        card_set_code = match.group(1) if match else ""
        card_set_number = match.group(2) if match else ""
        card_finish = details.get("finish", "").lower()
        card_set_name = details.get("set_name", "")

        if set_name and card_set_name.lower() != set_name.lower():
            continue
        if set_code and card_set_code.lower() != set_code.lower():
            continue
        if number and card_set_number != number:
            continue
        if foil is not None and foil != ("foil" in card_finish):
            continue

        results.append((
            price,
            f"{product_name} ({card_set_name}, {details.get('finish')})",
            f"https://www.mtgmate.com.au{link_path}",
        ))

    if not results:
        return (0.0, "Out of stock", "")
    return min(results, key=lambda x: x[0])
