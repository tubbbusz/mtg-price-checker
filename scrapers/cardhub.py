import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from .gg import _extract_base_name, _is_foil_title


def scrape_cardhub(card_name: str, set_code=None, number=None, foil=None):
    target = _extract_base_name(card_name)
    base_url = "https://thecardhubaustralia.com.au"
    query = quote_plus(card_name)
    url = f"{base_url}/search?type=product&options%5Bprefix%5D=last&q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []

        for card in soup.select("div[data-product-variants]"):
            # Get product title from the visible card
            title_tag = card.find_next_sibling().select_one(".grid-view-item__title") if card.find_next_sibling() else None
            # Try parent card
            parent = card.find_parent("div", class_=re.compile("product-card"))
            if parent:
                title_tag = parent.select_one(".grid-view-item__title")

            # Fallback: get name from variant data
            variants_raw = card.get("data-product-variants", "[]")
            try:
                variants = json.loads(variants_raw.replace("&quot;", '"'))
            except Exception:
                continue

            if not variants:
                continue

            # Get card name from first variant
            first_name = variants[0].get("name", "")
            prod_title = first_name.split(" - ")[0].strip() if " - " in first_name else first_name
            if _extract_base_name(prod_title) != target:
                continue

            # Tags contain set code and collector number
            tags_raw = card.get("data-product-tags", "[]")
            try:
                tags = json.loads(tags_raw.replace("&quot;", '"'))
            except Exception:
                tags = []

            # Set code filter — tags include set code like "EOC", "WOE" etc
            if set_code:
                if not any(t.upper() == set_code.upper() for t in tags):
                    continue

            # Number filter — tags include collector number as string like "57"
            if number:
                if not any(t == number for t in tags):
                    continue

            # Product URL
            prod_id = card.get("data-product-id", "")
            handle_tag = card.find_parent("a", href=re.compile("/products/"))
            prod_url = ""
            # Try to find link in nearby sibling
            next_sib = card.find_next_sibling()
            if next_sib:
                link = next_sib.select_one("a[href*='/products/']")
                if link:
                    prod_url = base_url + link["href"].split("?")[0]

            # Process each available NM variant
            for v in variants:
                if not v.get("available", False):
                    continue
                vtitle = v.get("title", "")
                if "near mint" not in vtitle.lower():
                    continue
                is_foil = "foil" in vtitle.lower() or "foil" in v.get("name", "").lower()
                if foil is True and not is_foil:
                    continue
                if foil is False and is_foil:
                    continue
                try:
                    price = float(v.get("price", 0)) / 100
                except Exception:
                    continue
                if price <= 0:
                    continue
                vid = v.get("id")
                vurl = f"{prod_url}?variant={vid}" if prod_url and vid else (prod_url or url)
                results.append((price, f"{prod_title} — {vtitle}", vurl))

        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception as e:
        return 0.0, "Error", ""