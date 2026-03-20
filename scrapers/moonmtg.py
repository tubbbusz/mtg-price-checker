import re
import requests
from bs4 import BeautifulSoup
from .utils import parse_card_query

BASE_URL = "https://moonmtg.com/products/"


def _make_handle(card_name: str) -> str:
    h = card_name.lower()
    h = re.sub(r"[''\":,?!()]", "", h)
    h = re.sub(r"[^a-z0-9\s-]", "", h)
    h = re.sub(r"\s+", "-", h)
    return h.strip("-")


def _parse_public_title(title: str):
    """Parse "SLD 606 Foil" -> (set_code, number, is_foil)"""
    parts = title.strip().split()
    set_code = parts[0].upper() if parts else ""
    number = parts[1] if len(parts) > 1 else ""
    is_foil = "foil" in title.lower()
    return set_code, number, is_foil


def _check_variant_stock(handle: str, vid) -> bool:
    """Check if a specific variant is in stock via its product page."""
    try:
        r = requests.get(f"{BASE_URL}{handle}?variant={vid}", timeout=10)
        if r.status_code != 200:
            return False
        soup = BeautifulSoup(r.text, "html.parser")
        inv = soup.find("p", class_="product__inventory")
        if inv:
            text = inv.get_text(strip=True)
            return text not in ("Out of stock", "Sold out")
        # Also check add to cart button
        btn = soup.select_one("button[name='add']")
        if btn:
            return not btn.has_attr("disabled")
        return True  # optimistic if no indicator found
    except Exception:
        return False


def scrape_moonmtg(query: str):
    card_name, set_code, number, foil, etched = parse_card_query(query)
    handle = _make_handle(card_name)

    # Fetch product JSON
    try:
        r = requests.get(f"{BASE_URL}{handle}.json", timeout=15)
        if r.status_code != 200:
            return (0.0, "Not found", "")
        product = r.json().get("product", {})
    except Exception:
        return (0.0, "Error", "")

    variants = product.get("variants", [])
    candidates = []

    for v in variants:
        public_title = v.get("option1") or v.get("title", "")
        v_set, v_num, v_foil = _parse_public_title(public_title)

        # Price — .json returns as string e.g. "45.40"
        try:
            price = float(v.get("price", 0))
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

        # Check availability
        # .json has 'available' field on Shopify — use it if present
        available = v.get("available")
        if available is False:
            continue
        elif available is None:
            # Not in .json — check variant page (slow but accurate)
            if not _check_variant_stock(handle, vid):
                continue

        candidates.append((price, label, url))

    if candidates:
        return min(candidates, key=lambda x: x[0])
    return (0.0, "Out of stock", "")