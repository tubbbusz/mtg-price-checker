import re
import json
import requests
from .gg import _parse_sku, _extract_base_name, _get_set_from_title, _is_foil_title, _norm_gg
from .utils import normalize
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


def scrape_gamesportal(card_name: str, set_code=None, number=None, foil=None):
    target = _extract_base_name(card_name)
    base_url = "https://gamesportal.com.au"
    query = quote_plus(card_name)
    search_url = f"{base_url}/search?type=product&q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(search_url, headers=headers, timeout=15)
        r.raise_for_status()
        page_text = r.text
        results = []

        # Primary: data-events with SKU
        m = re.search(r'data-events="([^"]+)"', page_text)
        print(f"[GP] data-events found={m is not None} url={search_url}")
        if m:
            try:
                raw = m.group(1).replace("&quot;", '"')
                events = json.loads(raw)
                print(f"[GP] events parsed ok, count={len(events)}")
                for event in events:
                    if len(event) >= 2 and isinstance(event[1], dict):
                        variants = event[1].get("searchResult", {}).get("productVariants", [])
                        print(f"[GP] variants in event: {len(variants)}")
                        for v in variants[:2]:
                            print(f"[GP]   title={v.get('product',{}).get('title','')!r} vendor={v.get('product',{}).get('vendor','')!r}")
                for event in events:
                    if len(event) < 2 or not isinstance(event[1], dict):
                        continue
                    for v in event[1].get("searchResult", {}).get("productVariants", []):
                        prod = v.get("product", {})
                        if prod.get("vendor", "") != "Magic: The Gathering":
                            continue
                        prod_title = prod.get("title", "")
                        if _extract_base_name(prod_title) != target:
                            continue
                        sku = v.get("sku", "")
                        sku_set, sku_num, sku_foil = _parse_sku(sku)
                        if set_code and sku_set and sku_set.lower() != set_code.lower():
                            continue
                        if number and sku_num and sku_num != number:
                            continue
                        is_foil = sku_foil if sku_foil is not None else "foil" in v.get("title", "").lower()
                        if foil is True and not is_foil:
                            continue
                        if foil is False and is_foil:
                            continue
                        try:
                            price = float(v.get("price", {}).get("amount", 0))
                        except Exception:
                            continue
                        if price <= 0:
                            continue
                        prod_path = prod.get("url", "").split("?")[0]
                        prod_url = f"{base_url}{prod_path}" if prod_path.startswith("/") else prod_path
                        results.append((price, f"{prod_title} — {v.get('title','')}", prod_url))
            except Exception:
                pass

        print(f"[GP] data-events results={len(results)} target={target!r}")
        if results:
            return min(results, key=lambda x: x[0])

        # Fallback: HTML product cards
        soup = BeautifulSoup(page_text, "html.parser")
        for card in soup.select("div.product-card-list2"):
            title_tag = card.select_one(".grid-view-item__title")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if _extract_base_name(title) != target:
                continue
            if card.select_one(".outstock-overlay"):
                continue
            if "grid-view-item--sold-out" in " ".join(card.get("class", [])):
                continue
            title_is_foil = _is_foil_title(title)
            if foil is True and not title_is_foil:
                continue
            if foil is False and title_is_foil:
                continue
            link_tag = card.select_one("a[href]")
            link = base_url + link_tag["href"] if link_tag and link_tag["href"].startswith("/") else ""
            price_tag = card.select_one(".product-price__price")
            if not price_tag:
                continue
            pm = re.search(r"\$([\d.,]+)", price_tag.get_text())
            if not pm:
                continue
            price = float(pm.group(1).replace(",", ""))
            results.append((price, title, link))

        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception:
        return 0.0, "Error", ""