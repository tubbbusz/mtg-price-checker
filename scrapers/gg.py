import re
import json
import html as html_module
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from .utils import normalize
from .setnames import get_set_name


def _extract_base_name(title):
    title = title.split(" - ")[0]
    title = re.sub(r"\[.*?\]", "", title)
    title = re.sub(r"\(.*?\)", "", title)
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s-]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def _is_foil_title(title):
    return "foil" in title.split(" - ")[-1].lower()


def _get_set_from_title(title):
    m = re.search(r"\[([^\]]+)\]", title)
    return m.group(1).strip() if m else ""


def _find_matching_bracket(text, open_pos):
    n = len(text)
    if open_pos < 0 or open_pos >= n or text[open_pos] != "{":
        return -1
    depth = 0; in_str = False; str_char = None; esc = False
    for i in range(open_pos, n):
        ch = text[i]
        if esc: esc = False; continue
        if ch == "\\" and in_str: esc = True; continue
        if ch in ('"', "'"):
            if not in_str: in_str = True; str_char = ch
            elif ch == str_char: in_str = False; str_char = None
            continue
        if not in_str:
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0: return i
    return -1


def _norm_gg(text):
    text = html_module.unescape(text)
    text = text.lower()
    text = re.sub(r"[''`]", "", text)
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── GG Adelaide + Modbury ────────────────────────────────────────────────────

def scrape_gg(card_name, base_url, set_code=None, number=None, foil=None):
    target = _extract_base_name(card_name)
    target_set_name = get_set_name(set_code).lower() if set_code else None
    query = quote_plus(f'{card_name} product_type:"mtg"')
    url = f"{base_url}/search?q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for div in soup.select("div.addNow.single"):
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
            if foil is True and not title_is_foil:
                continue
            if foil is False and title_is_foil:
                continue
            if target_set_name and target_set_name not in title_set and title_set not in target_set_name:
                continue
            results.append((price, full_title, url))

        if not results:
            return 0.0, "Out of stock", ""
        return min(results, key=lambda x: x[0])
    except Exception:
        return 0.0, "Error", ""


def scrape_ggadelaide(card_name, set_code=None, number=None, foil=None):
    return scrape_gg(card_name, "https://ggadelaide.com.au", set_code, number, foil)


def scrape_ggmodbury(card_name, set_code=None, number=None, foil=None):
    return scrape_gg(card_name, "https://ggmodbury.com.au", set_code, number, foil)


# ── GG Australia ─────────────────────────────────────────────────────────────

def scrape_ggaustralia(card_name, set_code=None, number=None, foil=None):
    target = _norm_gg(card_name)
    target_set_name = get_set_name(set_code).lower() if set_code else None

    query = quote_plus(card_name)
    search_url = f"https://tcg.goodgames.com.au/search?q={query}&f_Product%20Type=mtg+single"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(search_url, headers=headers, timeout=15)
        r.raise_for_status()
    except Exception:
        return 0.0, "Error", ""

    page_text = r.text
    soup = BeautifulSoup(page_text, "html.parser")
    results = []

    # Method 1: st-product HTML cards (server-rendered, reliable)
    all_cards = soup.select("div.st-product")
    print(f"[GGAus] page status={r.status_code} size={len(page_text)} st-product cards={len(all_cards)}")
    for card in all_cards:
        title_tag = card.select_one("div.product-title a span") or card.select_one("div.product-title a")
        if not title_tag:
            continue
        full_title = html_module.unescape(title_tag.get_text(strip=True))
        base_title = re.sub(r"\(.*?\)", "", full_title.split("[")[0]).strip()
        print(f"[GGAus]   card: {full_title!r} base={base_title!r} target={target!r} match={target == _norm_gg(base_title)}")
        if target != _norm_gg(base_title):
            continue

        set_tag = card.select_one("div.st-subtitle")
        card_set = set_tag.get_text(strip=True).lower() if set_tag else _get_set_from_title(full_title).lower()
        if target_set_name and target_set_name not in card_set and card_set not in target_set_name:
            continue

        # Foil: product-inner has "foiled" class, or title parenthetical contains "foil"
        inner = card.select_one("div.product-inner")
        inner_foiled = inner is not None and "foiled" in inner.get("class", [])
        title_foiled = any("foil" in p.lower() for p in re.findall(r"\(([^)]+)\)", full_title))
        card_is_foil = inner_foiled or title_foiled

        if foil is True and not card_is_foil:
            continue
        if foil is False and card_is_foil:
            continue

        price_tag = card.select_one("div.product-prices.no-sale span")
        if not price_tag:
            continue
        pm = re.search(r"\$([\d,]+\.?\d*)", price_tag.get_text())
        if not pm:
            continue
        try:
            price = float(pm.group(1).replace(",", ""))
        except ValueError:
            continue
        if price <= 0:
            continue

        link_tag = card.select_one("div.product-title a")
        href = link_tag.get("href", "") if link_tag else ""
        if href and not href.startswith("http"):
            href = "https://tcg.goodgames.com.au" + href
        results.append((price, full_title, href))

    if results:
        return min(results, key=lambda x: x[0])

    # Method 2: Spurit blocks (some cards use this)
    key_pattern = re.compile(
        r"Spurit\.Preorder2\.snippet\.products\[['\"][^'\"]+['\"]\]\s*=\s*"
        r"(\{[^;]{1,20000}\})\s*;"
    )
    for m in key_pattern.finditer(page_text):
        try:
            obj = json.loads(m.group(1))
        except Exception:
            continue
        title = obj.get("title", "")
        base_title = re.sub(r"\(.*?\)", "", title.split("[")[0]).strip()
        if target != _norm_gg(base_title):
            continue
        title_set = _get_set_from_title(title).lower()
        if target_set_name and target_set_name not in title_set and title_set not in target_set_name:
            continue
        handle = obj.get("handle", "")
        for v in obj.get("variants", []):
            if int(v.get("inventory_quantity", 0) or 0) <= 0:
                continue
            vtitle = v.get("title", "")
            if "near mint" not in vtitle.lower():
                continue
            variant_is_foil = "foil" in vtitle.lower()
            if foil is True and not variant_is_foil:
                continue
            if foil is False and variant_is_foil:
                continue
            try:
                price = float(v.get("price", 0)) / 100.0
            except Exception:
                continue
            if price <= 0:
                continue
            vid = v.get("id")
            product_url = f"https://tcg.goodgames.com.au/products/{handle}"
            if vid:
                product_url += f"?variant={vid}"
            results.append((price, f"{title} — {vtitle}", product_url))

    if not results:
        return 0.0, "Out of stock", ""
    return min(results, key=lambda x: x[0])
