import re
import json
import requests
from .utils import normalize
from .gg import _parse_sku, _extract_base_name


def scrape_cardhub(card_name: str, set_code=None, number=None, foil=None):
    """
    CardHub uses data-events like GamesPortal but with numeric SKUs.
    Title format: 'Sol Ring (57)(Commander: Lorwyn Eclipsed)'
    Collector number is in the first parenthetical.
    No set code in SKU, so set filtering uses title matching.
    """
    target = _extract_base_name(card_name)
    base_url = "https://thecardhubaustralia.com.au"
    query = card_name.replace(" ", "+")
    search_url = f"{base_url}/search?type=product&q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(search_url, headers=headers, timeout=15)
        r.raise_for_status()
        page_text = r.text
        results = []

        m = re.search(r'data-events="([^"]+)"', page_text)
        if m:
            try:
                events = json.loads(m.group(1).replace("&quot;", '"'))
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

                        # Extract collector number from title parenthetical
                        # e.g. "Sol Ring (57)(Commander: Lorwyn Eclipsed)" -> "57"
                        parens = re.findall(r"\((\d+)\)", prod_title)
                        title_number = parens[0] if parens else None

                        if number and title_number and title_number != number:
                            continue

                        # Foil from variant title
                        vtitle = v.get("title", "")
                        is_foil = "foil" in vtitle.lower()
                        if foil is True and not is_foil:
                            continue
                        if foil is False and is_foil:
                            continue

                        # Set code filtering — match against title set name
                        # CardHub has no set code in SKU, so skip set_code filter
                        # (could add set name lookup later)

                        try:
                            price = float(v.get("price", {}).get("amount", 0))
                        except Exception:
                            continue
                        if price <= 0:
                            continue

                        prod_path = prod.get("url", "").split("?")[0]
                        prod_url = f"{base_url}{prod_path}" if prod_path.startswith("/") else prod_path
                        results.append((price, f"{prod_title} — {vtitle}", prod_url))
            except Exception:
                pass

        print(f"[CH] data-events results={len(results)} target={target!r}")
        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception as e:
        print(f"[CH] exception: {e}")
        return 0.0, "Error", ""
