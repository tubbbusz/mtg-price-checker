import re
import requests
from .utils import parse_card_query

BASE_URL = "https://moonmtg.com/products/"


def _make_handle(card_name: str) -> str:
    h = card_name.lower()
    h = re.sub(r"[''\":,?!()]", "", h)
    h = re.sub(r"[^a-z0-9\s-]", "", h)
    h = re.sub(r"\s+", "-", h)
    return h.strip("-")


def _parse_public_title(title: str):
    """
    Parse MoonMTG variant public_title like "SLD 606 Foil" or "FIC 361"
    Returns (set_code, number, is_foil)
    """
    parts = title.strip().split()
    set_code = parts[0].upper() if parts else ""
    number = parts[1] if len(parts) > 1 else ""
    is_foil = "foil" in title.lower()
    return set_code, number, is_foil


def scrape_moonmtg(query: str):
    card_name, set_code, number, foil, etched = parse_card_query(query)
    handle = _make_handle(card_name)

    # Fetch product JSON — has all variants with availability
    try:
        r = requests.get(f"{BASE_URL}{handle}.json", timeout=15)
        if r.status_code != 200:
            return (0.0, "Not found", "")
        product = r.json().get("product", {})
    except Exception:
        return (0.0, "Error", "")

    variants = product.get("variants", [])
    results = []

    for v in variants:
        if not v.get("available", False):
            continue

        public_title = v.get("option1", "") or v.get("title", "")
        v_set, v_num, v_foil = _parse_public_title(public_title)

        try:
            price = float(v.get("price", 0)) / 100
        except Exception:
            continue
        if price <= 0:
            continue

        # Set filter
        if set_code and v_set and v_set.lower() != set_code.lower():
            continue

        # Number filter
        if number and v_num and v_num != number:
            continue

        # Foil filter
        if foil is True and not v_foil:
            continue
        if (foil is False or foil is None) and v_foil:
            continue

        vid = v.get("id")
        url = f"{BASE_URL}{handle}?variant={vid}"
        label = v.get("name", f"{card_name} - {public_title}")
        results.append((price, label, url))

    if results:
        return min(results, key=lambda x: x[0])
    return (0.0, "Out of stock", "")
