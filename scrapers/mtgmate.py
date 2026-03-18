import re
import json
import cloudscraper
from bs4 import BeautifulSoup
from .utils import normalize, parse_card_query


def fetch_mtgmate_price(card_name: str, set_name: str = None, set_code: str = None,
                        number: str = None, foil: bool = None):

    # MTGMate has a direct card URL if we have set_code + number
    # e.g. /cards/Sol_Ring/AFC/215 or /cards/Sol_Ring/AFC/215:foil
    # Try direct URL first if we have enough info
    scraper = cloudscraper.create_scraper()

    if set_code and number:
        safe_name = re.sub(r'[^a-zA-Z0-9\s]', '', card_name)
        safe_name = re.sub(r'\s+', '_', safe_name.strip())
        base_url = f"https://www.mtgmate.com.au/cards/{safe_name}/{set_code.upper()}/{number}"

        results = []
        for suffix, is_foil in [("", False), (":foil", True)]:
            # Skip if foil filter doesn't match
            if foil is True and not is_foil:
                continue
            if foil is False and is_foil:
                continue

            try:
                url = base_url + suffix
                r = scraper.get(url, timeout=20)
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")

                # Check in stock
                container = soup.find("div", {"data-react-class": "FilterableTable"})
                if container:
                    props = json.loads(container.get("data-react-props", "{}"))
                    for uuid_data in props.get("uuid", {}).values():
                        qty = uuid_data.get("quantity", 0)
                        if qty <= 0:
                            continue
                        try:
                            price = int(uuid_data.get("price", 0)) / 100
                        except Exception:
                            continue
                        if price <= 0:
                            continue
                        finish = uuid_data.get("finish", "").lower()
                        card_is_foil = "foil" in finish
                        if foil is True and not card_is_foil:
                            continue
                        if foil is False and card_is_foil:
                            continue
                        results.append((price, uuid_data.get("name", card_name), url))
            except Exception:
                continue

        if results:
            return min(results, key=lambda x: x[0])

    # Fallback: search page
    search_url = f"https://www.mtgmate.com.au/cards/search?q={card_name.replace(' ', '+')}"
    try:
        r = scraper.get(search_url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        return (0.0, f"Error: {e}", "")

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

    for card_id, details in uuid_map.items():
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

        # Set code from direct field (lowercase in MTGMate)
        card_set_code = details.get("set_code", "")
        # Number from link_path
        link_path = details.get("link_path", "")
        match = re.search(r"/(\d+[a-z]*)(?::foil)?$", link_path)
        card_number = match.group(1) if match else ""
        card_finish = details.get("finish", "").lower()
        card_is_foil = "foil" in card_finish
        card_set_name = details.get("set_name", "")

        if set_name and card_set_name.lower() != set_name.lower():
            continue
        if set_code and card_set_code.lower() != set_code.lower():
            continue
        if number and card_number != number:
            continue
        if foil is True and not card_is_foil:
            continue
        if foil is False and card_is_foil:
            continue

        results.append((
            price,
            f"{product_name} ({card_set_name}, {details.get('finish')})",
            f"https://www.mtgmate.com.au{link_path}",
        ))

    if not results:
        return (0.0, "Out of stock", "")
    return min(results, key=lambda x: x[0])
