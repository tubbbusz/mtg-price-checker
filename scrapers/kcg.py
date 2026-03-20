import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from .gg import _extract_base_name, _get_set_from_title
from .setnames import get_set_name

BASE_URL = "https://kastlecardsandgames.com"


def _parse_kcg_sku(sku):
    """
    Parse KCG SKU: MTG-EN-{SET}-{NUM}-{variant?}-{FO/NO}-{condition}
    Returns (set_code, number, is_foil) or (None, None, None)
    """
    parts = sku.split("-")
    if len(parts) < 4:
        return None, None, None
    # Find FO/NO position (second to last)
    fo_no = parts[-2].upper() if len(parts) >= 2 else ""
    is_foil = fo_no == "FO"
    set_code = parts[2] if len(parts) > 2 else None
    number = parts[3] if len(parts) > 3 else None
    return set_code, number, is_foil


def scrape_kcg(card_name: str, set_code=None, number=None, foil=None):
    target = _extract_base_name(card_name)
    target_set_name = get_set_name(set_code).lower() if set_code else None
    query = quote_plus(card_name)
    search_url = f"{BASE_URL}/search?type=product&q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(search_url, headers=headers, timeout=15)
        r.raise_for_status()
        page_text = r.text
        soup = BeautifulSoup(page_text, "html.parser")

        # Build map of product_id -> default_variant_id and stock status from HTML cards
        card_stock = {}  # product_id -> {variant_id: is_available}
        for card in soup.select("product-card"):
            pid = card.get("data-product-id", "")
            link = card.select_one("a.product-card__link")
            href = link.get("href", "") if link else ""
            vm = re.search(r'variant=(\d+)', href)
            vid = int(vm.group(1)) if vm else None
            add_btn = card.select_one("button[data-action='add-to-cart'], .quick-add__button--add")
            is_available = not (add_btn and add_btn.has_attr("disabled")) if add_btn else True
            if pid and vid:
                card_stock.setdefault(pid, {})[vid] = is_available

        # Parse ShopifyAnalytics.meta for full variant/SKU data
        meta_match = re.search(
            r'var meta\s*=\s*(\{"products"\s*:.*?\})\s*;',
            page_text, re.S
        )
        results = []
        if meta_match:
            meta = json.loads(meta_match.group(1))
            for prod in meta.get("products", []):
                pid = str(prod.get("id", ""))
                handle = prod.get("handle", "")
                prod_stock = card_stock.get(pid, {})

                for v in prod.get("variants", []):
                    sku = v.get("sku", "")
                    sku_set, sku_num, sku_foil = _parse_kcg_sku(sku)

                    # NM only (condition = 1)
                    if not sku.endswith("-1"):
                        continue

                    # Name match
                    full_name = v.get("name", "")
                    prod_title = full_name.split(" - ")[0].strip() if " - " in full_name else full_name
                    if _extract_base_name(prod_title) != target:
                        continue

                    # Set filter
                    if set_code and sku_set and sku_set.lower() != set_code.lower():
                        # Also try set name from title
                        title_set = _get_set_from_title(prod_title).lower()
                        if not (target_set_name and (target_set_name in title_set or title_set in target_set_name)):
                            continue

                    # Number filter
                    if number and sku_num and sku_num != number:
                        continue

                    # Foil filter
                    if foil is True and not sku_foil:
                        continue
                    if foil is False and sku_foil:
                        continue

                    # Stock check from HTML card (only for default variant)
                    vid = v.get("id")
                    if vid in prod_stock:
                        if not prod_stock[vid]:
                            continue
                    # If not in prod_stock, we can't verify — include it optimistically

                    try:
                        price = float(v.get("price", 0)) / 100
                    except Exception:
                        continue
                    if price <= 0:
                        continue

                    vurl = f"{BASE_URL}/products/{handle}?variant={vid}"
                    results.append((price, prod_title, vurl))

        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception as e:
        return 0.0, "Error", ""
