import re
import json
import html as html_module
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
from .utils import normalize, parse_card_query
from .setnames import get_set_name


def _extract_base_name(title):
    """Extract card name from GG title format: 'Name (variant) [Set] - Condition'"""
    title = title.split(" - ")[0]          # remove condition
    title = re.sub(r"\[.*?\]", "", title)  # remove [Set Name]
    title = re.sub(r"\(.*?\)", "", title)  # remove (variant)
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s-]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def _is_foil_title(title: str) -> bool:
    """Check if a GG title indicates a foil card."""
    # Condition part is after the last ' - '
    # e.g. 'Sol Ring [Set] - Near Mint Foil'
    condition = title.split(" - ")[-1].lower()
    return "foil" in condition


def _get_set_from_title(title: str) -> str:
    """Extract set name from GG title brackets."""
    m = re.search(r"\[([^\]]+)\]", title)
    return m.group(1).strip() if m else ""


def scrape_gg(card_name, base_url, set_code=None, number=None, foil=None):
    target = _extract_base_name(card_name)

    # Resolve set name from code for matching
    target_set_name = get_set_name(set_code).lower() if set_code else None

    query = quote_plus(f'{card_name} product_type:"mtg"')
    url = f"{base_url}/search?q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        results = []
        items = soup.select("div.addNow.single")

        for div in items:
            onclick = div.get("onclick", "")
            match = re.search(r"addToCart\([^,]+,'([^']+)'", onclick)
            full_title = match.group(1).strip() if match else "N/A"

            price_tag = div.find("p")
            price_text = price_tag.get_text(strip=True) if price_tag else ""
            pm = re.search(r"\$([\d.,]+)", price_text)
            price = float(pm.group(1).replace(",", "")) if pm else 0.0

            if _extract_base_name(full_title) != target:
                continue

            title_is_foil = _is_foil_title(full_title)
            title_set = _get_set_from_title(full_title).lower()

            # Foil filter
            if foil is True and not title_is_foil:
                continue
            if foil is False and title_is_foil:
                continue

            # Set filter (match on full set name)
            if target_set_name and target_set_name not in title_set and title_set not in target_set_name:
                continue

            # GG doesn't have collector numbers in titles, so skip number filter

            results.append((price, full_title, url))

        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception:
        return 0.0, "Error", ""


def scrape_ggadelaide(card_name: str, set_code=None, number=None, foil=None):
    return scrape_gg(card_name, "https://ggadelaide.com.au", set_code, number, foil)


def scrape_ggmodbury(card_name: str, set_code=None, number=None, foil=None):
    return scrape_gg(card_name, "https://ggmodbury.com.au", set_code, number, foil)


def _find_matching_bracket(text: str, open_pos: int) -> int:
    n = len(text)
    if open_pos < 0 or open_pos >= n or text[open_pos] != "{":
        return -1
    depth = 0
    in_str = False
    str_char = None
    esc = False
    for i in range(open_pos, n):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch in ('"', "'"):
            if not in_str:
                in_str = True
                str_char = ch
            elif ch == str_char:
                in_str = False
                str_char = None
            continue
        if not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
    return -1


def scrape_ggaustralia(card_name: str, set_code=None, number=None, foil=None):
    def norm(text):
        text = html_module.unescape(text)
        text = text.lower()
        text = re.sub(r"[''`]", "", text)
        text = re.sub(r"[^a-z0-9\s-]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def slugify(text):
        text = html_module.unescape(text)
        text = text.lower()
        text = re.sub(r"[''`]", "", text)
        text = re.sub(r"[^a-z0-9]+", "-", text)
        text = re.sub(r"-{2,}", "-", text)
        return text.strip("-")

    target = norm(card_name)
    target_set_name = get_set_name(set_code).lower() if set_code else None

    query = quote_plus(card_name)
    search_url = f"https://tcg.goodgames.com.au/search?q={query}&f_Product%20Type=mtg+single"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(search_url, headers=headers, timeout=15)
        r.raise_for_status()
        page_text = r.text
    except Exception:
        return 0.0, "Error", ""

    candidates = []
    key_pattern = re.compile(r"Spurit\.Preorder2\.snippet\.products\[\s*['\"]([^'\"]+)['\"]\s*\]\s*=", re.S)
    for m in key_pattern.finditer(page_text):
        after_eq = m.end()
        brace_pos = page_text.find("{", after_eq)
        if brace_pos == -1:
            continue
        end_pos = _find_matching_bracket(page_text, brace_pos)
        if end_pos == -1:
            continue
        block = page_text[brace_pos:end_pos + 1]
        fixed = re.sub(r'([{\s,])([A-Za-z0-9_]+)\s*:', r'\1"\2":', block)
        fixed = fixed.replace("'", '"')
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        try:
            obj = json.loads(fixed)
        except Exception:
            continue

        title = obj.get("title", "")
        base_title = title.split("[")[0].strip()
        if target != norm(base_title):
            continue

        # Set filter from title brackets
        title_set = _get_set_from_title(title).lower()
        if target_set_name and target_set_name not in title_set and title_set not in target_set_name:
            continue

        handle = obj.get("handle", "")
        for v in obj.get("variants", []):
            qty = int(v.get("inventory_quantity", 0) or 0)
            if qty <= 0:
                continue
            price_cents = v.get("price")
            if price_cents is None:
                continue
            try:
                price = float(price_cents) / 100.0
            except Exception:
                continue
            if price <= 0:
                continue

            variant_title = v.get("title", "").lower()
            variant_is_foil = "foil" in variant_title

            if foil is True and not variant_is_foil:
                continue
            if foil is False and variant_is_foil:
                continue

            variant_id = v.get("id")
            product_url = f"https://tcg.goodgames.com.au/products/{handle}"
            if variant_id:
                product_url += f"?variant={variant_id}"
            candidates.append((price, f"{title} — {v.get('title', '')}", product_url))

    if candidates:
        return min(candidates, key=lambda x: x[0])

    # JSON API fallback
    try:
        json_url = f"https://tcg.goodgames.com.au/search.json?q={query}&f_Product%20Type=mtg+single"
        r2 = requests.get(json_url, headers=headers, timeout=15)
        r2.raise_for_status()
        payload = r2.json()
        products = payload.get("product_data") or payload.get("products") or payload.get("data", {}).get("product_data", [])

        results = []
        for prod in products:
            if str(prod.get("brand", "")).lower() != "magic: the gathering":
                continue
            name = prod.get("name") or ""
            base_name = name.split("[")[0].strip()
            if target != norm(base_name):
                continue

            title_set = _get_set_from_title(name).lower()
            if target_set_name and target_set_name not in title_set and title_set not in target_set_name:
                continue

            try:
                price = float(prod.get("price", 0))
            except Exception:
                continue
            if price <= 0:
                continue

            prod_is_foil = "foil" in name.lower()
            if foil is True and not prod_is_foil:
                continue
            if foil is False and prod_is_foil:
                continue

            link = f"https://tcg.goodgames.com.au/products/{slugify(name)}"
            results.append((price, name, link))

        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception:
        return 0.0, "Error", ""
