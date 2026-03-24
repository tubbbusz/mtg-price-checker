import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from .gg import _extract_base_name, _get_set_from_title
from .setnames import get_set_name


def _scrape_shopify_variants(card_name, base_url, set_code=None, number=None, foil=None):
    """
    Scrape a Shopify store that embeds data-product-variants and data-product-tags.
    Foil is indicated by 'Foil' tag AND 'foil' in variant title.
    Set is matched against tags (full set name) or title brackets.
    Number is matched against title parentheticals.
    """
    target = _extract_base_name(card_name)
    target_set_name = get_set_name(set_code).lower() if set_code else None
    query = quote_plus(card_name)
    url = f"{base_url}/search?type=product&options%5Bprefix%5D=last&q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []

        for card in soup.select("div[data-product-variants]"):
            variants_raw = card.get("data-product-variants", "[]").replace("&quot;", '"')
            tags_raw = card.get("data-product-tags", "[]").replace("&quot;", '"')

            try:
                variants = json.loads(variants_raw)
                tags = [t.lower() for t in json.loads(tags_raw)]
            except Exception:
                continue

            if not variants:
                continue

            # Card name from first variant
            first_name = variants[0].get("name", "")
            prod_title = first_name.split(" - ")[0].strip() if " - " in first_name else first_name
            if _extract_base_name(prod_title) != target:
                continue

            # Product is foil if "foil" tag present
            prod_is_foil_type = "foil" in tags

            # Set filter — match tag against full set name
            if target_set_name:
                set_in_tags = any(target_set_name in t or t in target_set_name for t in tags)
                set_in_title = target_set_name in _get_set_from_title(prod_title).lower()
                if not set_in_tags and not set_in_title:
                    continue

            # Number filter — from title parenthetical like (0357) or (57)
            if number:
                parens = re.findall(r"\(0*(\d+)\)", prod_title)
                if not any(p == number for p in parens):
                    continue

            # Get product URL from nearby link
            prod_url = url
            link = card.find_previous("a", href=re.compile(r"/products/"))
            if not link:
                link = card.find_next("a", href=re.compile(r"/products/"))
            if link:
                href = link.get("href", "").split("?")[0]
                prod_url = f"{base_url}{href}" if href.startswith("/") else href

            # Process variants — prefer NM but accept best available condition
            COND_RANK = {"near mint": 0, "lightly played": 1, "moderately played": 2,
                         "heavily played": 3, "damaged": 4}
            best_v = None; best_rank = 99; best_price = None
            for v in variants:
                if not v.get("available", False):
                    continue
                vtitle = v.get("title", "")
                vtitle_lower = vtitle.lower()
                variant_is_foil = "foil" in vtitle_lower
                # Determine condition rank (strip foil suffix for matching)
                cond_key = re.sub(r"\s*foil\s*$", "", vtitle_lower).strip()
                rank = COND_RANK.get(cond_key, 99)
                if rank == 99:
                    continue  # unknown condition
                variant_is_foil = "foil" in vtitle_lower
                if foil is True and not variant_is_foil:
                    continue
                if foil is False and variant_is_foil:
                    continue
                try:
                    price = float(v.get("price", 0)) / 100
                except Exception:
                    continue
                if price <= 0:
                    continue
                if rank < best_rank or (rank == best_rank and (best_price is None or price < best_price)):
                    best_rank = rank; best_price = price
                    best_v = (price, f"{prod_title} — {vtitle}", f"{prod_url}?variant={v.get('id')}" if v.get('id') else prod_url)
            if best_v:
                results.append(best_v)

        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception as e:
        return 0.0, "Error", ""


def scrape_gamesportal(card_name: str, set_code=None, number=None, foil=None):
    return _scrape_shopify_variants(card_name, "https://gamesportal.com.au", set_code, number, foil)


def scrape_cardhub(card_name: str, set_code=None, number=None, foil=None):
    return _scrape_shopify_variants(card_name, "https://thecardhubaustralia.com.au", set_code, number, foil)
