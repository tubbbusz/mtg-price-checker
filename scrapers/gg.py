import re
import json
import html as html_module
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from .setnames import get_set_name

# Condition priority: lower = better
CONDITION_RANK = {"near mint": 0, "lightly played": 1, "moderately played": 2, "heavily played": 3, "damaged": 4}


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


def _parse_sku(sku):
    parts = sku.split("-")
    if len(parts) < 4:
        return None, None, None
    return parts[0].upper(), parts[1], parts[3] == "FO"


def _num_match(a, b):
    """Compare collector numbers ignoring leading zeros."""
    return a and b and a.lstrip('0') == b.lstrip('0')


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


def _parse_spurit_block(block):
    result = []
    i = 0; in_str = False; str_char = None
    while i < len(block):
        ch = block[i]
        if in_str:
            result.append(ch)
            if ch == "\\":
                i += 1
                if i < len(block): result.append(block[i])
            elif ch == str_char: in_str = False
            i += 1
        else:
            if ch in ('"', "'"):
                in_str = True; str_char = ch; result.append('"'); i += 1
            else:
                km = re.match(r'([A-Za-z_]\w*)\s*:', block[i:])
                if km and (not result or result[-1] in ('{', '[', ',', ' ', '\n', '\t')):
                    result.append('"'); result.append(km.group(1)); result.append('":')
                    i += len(km.group(0))
                else:
                    result.append(ch); i += 1
    fixed = ''.join(result)
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    try: return json.loads(fixed)
    except Exception: return None


SPURIT_KEY = re.compile(
    r"Spurit\.Preorder2\.snippet\.products\[['\"][^'\"]+['\"]\]\s*=\s*\{"
)


# ── GG Adelaide + Modbury ────────────────────────────────────────────────────

def scrape_gg(card_name, base_url, set_code=None, number=None, foil=None):
    target = _extract_base_name(card_name)
    target_set_name = get_set_name(set_code).lower() if set_code else None
    query = quote_plus(card_name)
    search_url = f"{base_url}/search?q={query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(search_url, headers=headers, timeout=15)
        response.raise_for_status()
        page_text = response.text
        results = []

        # Primary: data-events (has SKU, price, variant ID)
        m = re.search(r'data-events="([^"]+)"', page_text)
        if m:
            try:
                events = json.loads(m.group(1).replace("&quot;", '"'))
                for event in events:
                    if len(event) < 2 or not isinstance(event[1], dict):
                        continue
                    for v in event[1].get("searchResult", {}).get("productVariants", []):
                        prod = v.get("product", {})
                        prod_title = prod.get("title", "")
                        if _extract_base_name(prod_title) != target:
                            continue
                        sku = v.get("sku", "")
                        sku_set, sku_num, sku_foil = _parse_sku(sku)
                        if set_code and sku_set and sku_set.lower() != set_code.lower():
                            continue
                        if number and not _num_match(sku_num, number):
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
                        vid = v.get("id", "")
                        if vid:
                            prod_url = f"{prod_url}?variant={vid}"
                        results.append((price, f"{prod_title} — {v.get('title','')}", prod_url))
            except Exception:
                pass

        print(f"[GG] {base_url.split('//')[1]} data-events results={len(results)} set={set_code} num={number}")
        if results:
            return min(results, key=lambda x: x[0])

        # Fallback: collect handles from search page HTML, then fetch product.js per handle
        soup = BeautifulSoup(page_text, "html.parser")
        handles_seen = []

        # Collect handles from any product links on page
        for a in soup.select("a[href*='/products/']"):
            href = a.get("href", "")
            m2 = re.match(r"/products/([^/?#]+)", href)
            if m2:
                handle = m2.group(1)
                if handle not in handles_seen:
                    handles_seen.append(handle)

        # For set/number filtering, fetch product.js per handle
        print(f"[GG] handles found={len(handles_seen)} filtering by set={set_code} num={number}")
        if handles_seen and (set_code or number or foil is not None):
            for handle in handles_seen[:8]:
                try:
                    rp = requests.get(f"{base_url}/products/{handle}.js", headers=headers, timeout=10)
                    if rp.status_code != 200:
                        print(f"[GG] {handle} status={rp.status_code}")
                        continue
                    pdata = rp.json()
                    prod_title = pdata.get("title", handle)
                    prod_base = _extract_base_name(prod_title)
                    if prod_base != target:
                        print(f"[GG] {handle} name mismatch: {prod_base!r} != {target!r}")
                        continue
                    for v in pdata.get("variants", []):
                        avail = v.get("available", False)
                        vtitle = v.get("title", "")
                        sku = v.get("sku", "") or ""
                        sku_set, sku_num, sku_foil = _parse_sku(sku)
                        print(f"[GG]   variant: {vtitle!r} sku={sku!r} avail={avail} sku_set={sku_set} sku_num={sku_num}")
                        if not avail:
                            continue
                        if set_code and sku_set and sku_set.lower() != set_code.lower():
                            continue
                        if number and not _num_match(sku_num, number):
                            continue
                        is_foil = sku_foil if sku_foil is not None else "foil" in vtitle.lower()
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
                        vurl = f"{base_url}/products/{handle}?variant={vid}" if vid else f"{base_url}/products/{handle}"
                        results.append((price, f"{prod_title} — {vtitle}", vurl))
                except Exception as e:
                    print(f"[GG] {handle} error: {e}")
                    continue
            if results:
                return min(results, key=lambda x: x[0])

        # Fallback — use addNow.single prices from search HTML
        seen_vids = set()
        for div in soup.select("div.addNow.single"):
            onclick = div.get("onclick", "")
            # addToCart('variantId','Title','qty',1)
            oc_match = re.search(r"addToCart\('([^']+)','([^']+)'", onclick)
            if not oc_match:
                continue
            vid = oc_match.group(1)
            if vid in seen_vids:
                continue
            seen_vids.add(vid)
            full_title = oc_match.group(2).strip()
            price_tag = div.find("p")
            price_text = price_tag.get_text(strip=True) if price_tag else ""
            pm = re.search(r"\$([\d.,]+)", price_text)
            price = float(pm.group(1).replace(",", "")) if pm else 0.0
            if price <= 0:
                continue
            # Strip trailing condition suffix: "- NM", "- Foil - NM", etc.
            clean_title = re.sub(r"(\s*-\s*(NM|LP|MP|HP|DMG|damaged|heavily played|moderately played|lightly played|near mint))+\s*$", "", full_title, flags=re.I)
            # Detect condition for ranking (prefer NM over cheaper LP)
            cond_match = re.search(r"\b(near mint|lightly played|moderately played|heavily played|damaged|NM|LP|MP|HP|DMG)\b", price_text, re.I)
            cond_str = cond_match.group(1).lower() if cond_match else "near mint"
            cond_map = {"nm": "near mint", "lp": "lightly played", "mp": "moderately played", "hp": "heavily played", "dmg": "damaged"}
            cond_str = cond_map.get(cond_str, cond_str)
            cond_rank = CONDITION_RANK.get(cond_str, 99)
            # Name check — strip collector number before parens: "Sol Ring 871 (Set)" -> "Sol Ring"
            name_part = re.sub(r"\s+\d[\d/]*\s+(?=\()", " ", clean_title)
            name_part = re.sub(r"\s+\d[\d/]*\s*$", "", name_part)
            if _extract_base_name(name_part) != target:
                continue
            # Set filter — title format: "Card Name (Set Name)" or "Card Name 42/63 (Set Name)"
            if target_set_name:
                paren_match = re.search(r"\(([^)]+)\)\s*$", clean_title)
                title_set = paren_match.group(1).lower() if paren_match else ""
                if title_set and target_set_name not in title_set and title_set not in target_set_name:
                    continue
            is_foil = "foil" in full_title.lower()
            if foil is True and not is_foil:
                continue
            if foil is False and is_foil:
                continue
            results.append((cond_rank, price, clean_title, f"{search_url}&variant={vid}"))

        if not results:
            return 0.0, "Out of stock", ""
        best = min(results, key=lambda x: (x[0], x[1]))
        return best[1], best[2], best[3]
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

    # Get in-stock variant IDs from Spurit — but only use as a hint, not hard filter
    instock_ids = set()
    for m in SPURIT_KEY.finditer(page_text):
        brace_pos = m.end() - 1
        end_pos = _find_matching_bracket(page_text, brace_pos)
        if end_pos == -1: continue
        obj = _parse_spurit_block(page_text[brace_pos:end_pos + 1])
        if not obj: continue
        for v in obj.get("variants", []):
            if int(v.get("inventory_quantity", 0) or 0) > 0:
                instock_ids.add(int(v["id"]))

    meta_match = re.search(r'var meta\s*=\s*(\{"products"\s*:.*?\})\s*;', page_text, re.S)
    results = []
    handles_to_check = []  # handles where meta matched but variant not in Spurit

    if meta_match:
        try:
            meta = json.loads(meta_match.group(1))
            for prod in meta.get("products", []):
                handle = prod.get("handle", "")
                for v in prod.get("variants", []):
                    vid = int(v.get("id", 0))
                    sku = v.get("sku", "")
                    sku_set, sku_num, sku_foil = _parse_sku(sku)
                    if not sku.endswith("-1"):
                        continue
                    full_name = v.get("name", "")
                    prod_title = full_name.split(" - ")[0].strip() if " - " in full_name else full_name
                    base = re.sub(r"\(.*?\)", "", prod_title.split("[")[0]).strip()
                    if target != _norm_gg(base):
                        continue
                    if set_code and sku_set and sku_set.lower() != set_code.lower():
                        continue
                    if number and not _num_match(sku_num, number):
                        continue
                    is_foil = sku_foil if sku_foil is not None else "foil" in v.get("public_title", "").lower()
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

                    vurl = f"https://tcg.goodgames.com.au/products/{handle}?variant={vid}"
                    if instock_ids and vid in instock_ids:
                        # Confirmed in stock via Spurit
                        results.append((price, f"{prod_title} — {v.get('public_title','')}", vurl))
                    elif not instock_ids or handle not in [h for h, _ in handles_to_check]:
                        # Spurit didn't cover this variant — need to check product.js
                        handles_to_check.append((handle, prod_title))
        except Exception as e:
            print(f"[GGAus] meta parse error: {e}")

    if results:
        return min(results, key=lambda x: x[0])

    # Check product.js for handles where stock wasn't confirmed by Spurit
    for handle, prod_title in handles_to_check[:4]:
        try:
            rp = requests.get(
                f"https://tcg.goodgames.com.au/products/{handle}.js",
                headers=headers, timeout=10
            )
            rp.raise_for_status()
            pdata = rp.json()
            for v in pdata.get("variants", []):
                if not v.get("available", False):
                    continue
                vtitle = v.get("title", "")
                if "near mint" not in vtitle.lower():
                    continue
                sku = v.get("sku", "") or ""
                sku_set, sku_num, sku_foil = _parse_sku(sku)
                if set_code and sku_set and sku_set.lower() != set_code.lower():
                    continue
                if number and not _num_match(sku_num, number):
                    continue
                is_foil = sku_foil if sku_foil is not None else "foil" in vtitle.lower()
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
                vurl = f"https://tcg.goodgames.com.au/products/{handle}?variant={vid}"
                results.append((price, f"{prod_title} — {vtitle}", vurl))
        except Exception:
            continue

    # Spurit fallback
    if not results:
        for m in SPURIT_KEY.finditer(page_text):
            brace_pos = m.end() - 1
            end_pos = _find_matching_bracket(page_text, brace_pos)
            if end_pos == -1: continue
            obj = _parse_spurit_block(page_text[brace_pos:end_pos + 1])
            if not obj: continue
            title = obj.get("title", "")
            base_title = re.sub(r"\(.*?\)", "", title.split("[")[0]).strip()
            if target != _norm_gg(base_title): continue
            title_set = _get_set_from_title(title).lower()
            if target_set_name and target_set_name not in title_set and title_set not in target_set_name:
                continue
            handle = obj.get("handle", "")
            for v in obj.get("variants", []):
                if int(v.get("inventory_quantity", 0) or 0) <= 0: continue
                vtitle = v.get("title", "")
                if "near mint" not in vtitle.lower(): continue
                sku = v.get("sku", "")
                sku_set, sku_num, sku_foil = _parse_sku(sku) if sku else (None, None, None)
                if number and not _num_match(sku_num, number): continue
                is_foil = sku_foil if sku_foil is not None else "foil" in vtitle.lower()
                if foil is True and not is_foil: continue
                if foil is False and is_foil: continue
                try: price = float(v.get("price", 0)) / 100
                except Exception: continue
                if price <= 0: continue
                vid = v.get("id")
                vurl = f"https://tcg.goodgames.com.au/products/{handle}?variant={vid}" if vid else ""
                results.append((price, f"{title} — {vtitle}", vurl))

    if not results:
        return 0.0, "Out of stock", ""
    return min(results, key=lambda x: x[0])