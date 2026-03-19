import re
import json
import html as html_module
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
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


def _norm_gg(text):
    text = html_module.unescape(text)
    text = text.lower()
    text = re.sub(r"[''`]", "", text)
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_sku(sku: str):
    """
    Parse a GG SKU like 'MKM-148-EN-NF-1' into (set_code, collector_number, foil).
    SKU format: <SET>-<NUMBER>-<LANG>-<FOIL_FLAG>-<CONDITION>
    FOIL_FLAG: 'F' = foil, 'NF' = non-foil, 'EF' = etched foil
    Returns (set_code, collector_number, foil) or (None, None, None) if unparseable.
    """
    parts = sku.upper().split("-")
    # Need at least SET, NUMBER, LANG, FOIL_FLAG
    if len(parts) < 4:
        return None, None, None
    set_code = parts[0]
    collector_number = parts[1].lstrip("0")  # strip leading zeros for comparison
    foil_flag = parts[3]
    if foil_flag in ("F", "EF"):
        foil = True
    elif foil_flag == "NF":
        foil = False
    else:
        foil = None
    return set_code, collector_number, foil


def _sku_matches(sku: str, target_set_code: str | None, target_number: str | None):
    """
    Return True if the SKU's set+number match the targets (when provided).
    Comparison is case-insensitive; leading zeros on collector number are ignored.
    """
    if not target_set_code and not target_number:
        return True
    sku_set, sku_num, _ = _parse_sku(sku)
    if sku_set is None:
        return True  # can't determine — don't filter out
    if target_set_code and sku_set != target_set_code.upper():
        return False
    if target_number and sku_num != target_number.lstrip("0"):
        return False
    return True


def _find_matching_bracket(text, open_pos):
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


def _parse_spurit_block(block):
    result = []
    i = 0
    in_str = False
    str_char = None
    while i < len(block):
        ch = block[i]
        if in_str:
            result.append(ch)
            if ch == "\\":
                i += 1
                if i < len(block):
                    result.append(block[i])
            elif ch == str_char:
                in_str = False
            i += 1
        else:
            if ch in ('"', "'"):
                in_str = True
                str_char = ch
                result.append('"')
                i += 1
            else:
                km = re.match(r'([A-Za-z_]\w*)\s*:', block[i:])
                if km and (not result or result[-1] in ('{', '[', ',', ' ', '\n', '\t')):
                    result.append('"')
                    result.append(km.group(1))
                    result.append('":')
                    i += len(km.group(0))
                else:
                    result.append(ch)
                    i += 1
    fixed = ''.join(result)
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    try:
        return json.loads(fixed)
    except Exception:
        return None


SPURIT_KEY = re.compile(
    r"Spurit\.Preorder2\.snippet\.products\[['\"][^'\"]+['\"]\]\s*=\s*\{"
)


def _parse_all_spurit(page_text, target, target_set_name, set_code=None, number=None):
    """
    Parse all Spurit blocks matching target card name.

    When set_code and/or number are provided, variants are additionally filtered
    by SKU (e.g. 'MKM-148-EN-NF-1') so only the exact printing is returned.

    Returns (results_in_stock, matching_handles).
      results_in_stock: list of (price, vtitle, label, url) for in-stock NM variants
      matching_handles: all handles that matched the card name (regardless of stock)
    """
    results = []
    handles = set()

    for m in SPURIT_KEY.finditer(page_text):
        brace_pos = m.end() - 1
        end_pos = _find_matching_bracket(page_text, brace_pos)
        if end_pos == -1:
            continue
        block = page_text[brace_pos:end_pos + 1]
        obj = _parse_spurit_block(block)
        if not obj:
            continue

        title = obj.get("title", "")
        base_title = re.sub(r"\(.*?\)", "", title.split("[")[0]).strip()
        if target != _norm_gg(base_title):
            continue

        title_set = _get_set_from_title(title).lower()
        if target_set_name and target_set_name not in title_set and title_set not in target_set_name:
            continue

        handle = obj.get("handle", "")
        if handle:
            handles.add(handle)

        for v in obj.get("variants", []):
            qty = int(v.get("inventory_quantity", 0) or 0)
            if qty <= 0:
                continue
            vtitle = v.get("title", "")
            if "near mint" not in vtitle.lower():
                continue

            # ── Collector-number filter via SKU ──────────────────────────────
            sku = v.get("sku", "")
            if not _sku_matches(sku, set_code, number):
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
            results.append((price, vtitle, f"{title} — {vtitle}", product_url))

    return results, handles


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

            # ── Collector-number filter via SKU ──────────────────────────────
            # Adelaide/Modbury pages embed a data-sku or similar; try onclick for sku
            sku_match = re.search(r"'([A-Z0-9]+-\d+-[A-Z]+-[A-Z]+-\d+)'", onclick)
            if sku_match:
                sku = sku_match.group(1)
                if not _sku_matches(sku, set_code, number):
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
    search_url = (
        f"https://tcg.goodgames.com.au/search?q={query}"
        f"&f_Product%20Type=mtg+single"
    )
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(search_url, headers=headers, timeout=15)
        r.raise_for_status()
    except Exception:
        return 0.0, "Error", ""

    page_text = r.text

    # Parse all matching Spurit blocks — get in-stock results AND all handles
    # Pass set_code + number so SKU filtering happens inside
    all_variants, handles = _parse_all_spurit(
        page_text, target, target_set_name, set_code=set_code, number=number
    )

    # Filter by foil preference
    results = []
    for price, vtitle, label, url in all_variants:
        variant_is_foil = "foil" in vtitle.lower()
        if foil is True and not variant_is_foil:
            continue
        if foil is False and variant_is_foil:
            continue
        results.append((price, label, url))

    print(f"[GGAus] spurit={len(results)} handles={handles} foil={foil} set={set_code} num={number} card={card_name!r}")

    if results:
        return min(results, key=lambda x: x[0])

    # Fallback: fetch product.js for each matching handle to get full variant list
    print(f"[GGAus] trying product.js fallback for {handles}")
    for handle in handles:
        try:
            rp = requests.get(
                f"https://tcg.goodgames.com.au/products/{handle}.js",
                headers=headers, timeout=10
            )
            rp.raise_for_status()
            pdata = rp.json()
            prod_title = pdata.get("title", handle)
            for v in pdata.get("variants", []):
                if not v.get("available", False):
                    continue
                vtitle = v.get("title", "")
                if "near mint" not in vtitle.lower():
                    continue

                # ── Collector-number filter via SKU ──────────────────────────
                sku = v.get("sku", "")
                if not _sku_matches(sku, set_code, number):
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
                vurl = f"https://tcg.goodgames.com.au/products/{handle}?variant={vid}"
                results.append((price, f"{prod_title} — {vtitle}", vurl))
        except Exception as e:
            print(f"[GGAus] product.js error for {handle}: {e}")
            continue

    if not results:
        return 0.0, "Out of stock", ""
    return min(results, key=lambda x: x[0])