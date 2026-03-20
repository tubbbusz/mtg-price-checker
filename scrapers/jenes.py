import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from .gg import _extract_base_name
from .setnames import get_set_name


def scrape_jenesmtg(card_name: str, set_code=None, number=None, foil=None):
    """
    JenesMTG uses ShopifyAnalytics.meta with variant name format:
    "Card Name|Set Name|Collector Number"
    One variant per product (NM only). Foil products have "foil" in handle.
    """
    target = _extract_base_name(card_name)
    target_set_name = get_set_name(set_code).lower() if set_code else None
    base_url = "https://jenesmtg.com.au"
    query = quote_plus(card_name)
    search_url = f"{base_url}/search?type=product&q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(search_url, headers=headers, timeout=15)
        r.raise_for_status()
        page_text = r.text
        results = []

        # Parse ShopifyAnalytics.meta
        meta_match = re.search(
            r'var meta\s*=\s*(\{"products"\s*:.*?\})\s*;',
            page_text, re.S
        )
        if meta_match:
            try:
                meta = json.loads(meta_match.group(1))
                for prod in meta.get("products", []):
                    handle = prod.get("handle", "")

                    for v in prod.get("variants", []):
                        raw_name = v.get("name", "")
                        sku = v.get("sku", "")

                        # Foil detection:
                        # 1. SKU ends in FOIL
                        # 2. Handle starts with foil-
                        # 3. Title has "| ... Foil" suffix
                        prod_is_foil = (
                            sku.upper().endswith("FOIL") or
                            handle.lower().startswith("foil-") or
                            bool(re.search(r"\|\s*\w*\s*foil\s*$", raw_name, re.I))
                        )
                        if foil is True and not prod_is_foil:
                            continue
                        if foil is False and prod_is_foil:
                            continue

                        # Format: "Card Name|Set Name|Collector Number" or
                        #         "Card Name|Set Name|Number | Foil Type"
                        # Strip foil type suffix before splitting
                        clean_name = re.sub(r"\s*\|\s*\w[\w\s]*foil\s*$", "", raw_name, flags=re.I)
                        parts = clean_name.split("|")
                        if len(parts) < 1:
                            continue

                        v_card = parts[0].strip()
                        v_set = parts[1].strip().lower() if len(parts) > 1 else ""
                        v_num = parts[2].strip() if len(parts) > 2 else ""

                        if _extract_base_name(v_card) != target:
                            continue

                        # Set filter
                        if target_set_name:
                            if target_set_name not in v_set and v_set not in target_set_name:
                                continue

                        # Number filter
                        if number and v_num and v_num != number:
                            continue

                        try:
                            price = float(v.get("price", 0)) / 100
                        except Exception:
                            continue
                        if price <= 0:
                            continue

                        vid = v.get("id")
                        prod_url = f"{base_url}/products/{handle}?variant={vid}" if vid else f"{base_url}/products/{handle}"
                        label = f"{v_card} [{parts[1].strip() if len(parts) > 1 else ''}]"
                        if v_num:
                            label += f" #{v_num}"
                        results.append((price, label, prod_url))
            except Exception as e:
                pass

        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception:
        return 0.0, "Error", ""