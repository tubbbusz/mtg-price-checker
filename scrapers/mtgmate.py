import re
import json
import cloudscraper
from bs4 import BeautifulSoup
from .utils import normalize, parse_card_query


def _make_safe_name(card_name: str) -> str:
    """Convert card name to MTGMate URL format, preserving // for DFCs."""
    # Double-faced cards: 'A // B' -> 'A_//_B'
    name = card_name.replace(' // ', '_//_')
    # Replace remaining spaces with underscores, strip other special chars
    name = re.sub(r'[^a-zA-Z0-9_/]', '', name)
    name = re.sub(r'\s+', '_', name)
    return name


def fetch_mtgmate_price(card_name: str, set_name: str = None, set_code: str = None,
                        number: str = None, foil: bool = None):

    scraper = cloudscraper.create_scraper()

    # Try direct URL first if we have set_code + number
    if set_code and number:
        safe_name = _make_safe_name(card_name)
        base_url = f"https://www.mtgmate.com.au/cards/{safe_name}/{set_code.upper()}/{number}"

        # Decide which variants to try
        variants = []
        if foil is True:
            variants = [(":foil", True)]
        elif foil is False:
            variants = [("", False)]
        else:
            variants = [("", False), (":foil", True)]

        results = []
        for suffix, is_foil in variants:
            try:
                url = base_url + suffix
                r = scraper.get(url, timeout=20)
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                container = soup.find("div", {"data-react-class": "FilterableTable"})
                if not container:
                    continue
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
                    if is_foil != card_is_foil:
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

        card_set_code = details.get("set_code", "")
        link_path = details.get("link_path", "")
        num_match = re.search(r"/(\d+[a-z]*)(?::foil)?$", link_path)
        card_number = num_match.group(1) if num_match else ""
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
