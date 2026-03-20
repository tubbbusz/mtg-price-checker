import re
import requests
from bs4 import BeautifulSoup

HARERUYA_USER_TOKEN = "cc567a4aa1774b15fc1d2a4d94e5bc01fbb701c3f4c8e28085ba8a4661ec3867"
JPY_TO_AUD = 1 / 113.49

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.8",
    "Referer": "https://www.hareruyamtg.com/en/products/search",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
}

PAGE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[\u2018\u2019\u0027\":,?!()\[\]{}]", "", text)
    text = re.sub(r"[^a-z0-9\s\-]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _scrape_conditions_from_page(product_id: str, base_label: str, product_url: str, lang_code: str = "EN") -> list:
    try:
        r = requests.get(product_url, headers=PAGE_HEADERS, timeout=20)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    table_id = f"priceTable-{lang_code}"
    price_table = soup.select_one(f"#{table_id}")
    if not price_table:
        return []

    entries = []
    for row in price_table.select("div.row.not-first"):
        if row.select_one("a[href='/en/user_data/card_condition']"):
            continue
        if not row.select_one("button.addCart.detail"):
            continue

        cond_tag = row.select_one("a.productClassChange strong")
        if not cond_tag:
            continue
        cond = cond_tag.get_text(strip=True).upper()

        price_tag = row.select_one("div.col-xs-3")
        if not price_tag:
            continue
        price_match = re.search(r"[\d,]+", price_tag.get_text(strip=True))
        if not price_match:
            continue
        try:
            price_jpy = float(price_match.group().replace(",", ""))
        except ValueError:
            continue
        if price_jpy <= 0:
            continue

        stock_tag = row.select_one("div.col-xs-2")
        if not stock_tag:
            continue
        try:
            stock = int(stock_tag.get_text(strip=True))
        except ValueError:
            continue
        if stock <= 0:
            continue

        price_aud = round(price_jpy * JPY_TO_AUD, 2)
        entries.append((price_aud, f"{base_label} [{cond}]", product_url, int(price_jpy)))

    return entries


def scrape_hareruyamtg(card_name: str, language_filter: str = "EN",
                       set_code: str = None, number: str = None, foil: bool = None) -> tuple:
    from .setnames import get_set_name
    target_set_name = get_set_name(set_code).lower() if set_code else None

    base_url = "https://www.hareruyamtg.com/en/products/search/unisearch_api"
    params = {"kw": card_name, "fq.price": "1~*", "rows": 60, "page": 1, "user": HARERUYA_USER_TOKEN}

    docs = []
    page = 1
    while True:
        params["page"] = page
        try:
            r = requests.get(base_url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return (0.0, "Error", "", 0)

        page_docs = data.get("response", {}).get("docs", [])
        if not page_docs:
            break
        docs.extend(page_docs)
        total = int(data.get("response", {}).get("numFound", 0))
        if len(docs) >= total:
            break
        page += 1

    if not docs:
        return (0.0, "Not found", "", 0)

    target = _normalize(card_name)
    en_candidates, jp_candidates, other_candidates = [], [], []
    oos_fallback_en, oos_fallback_jp, oos_fallback_other = [], [], []

    for item in docs:
        lang_str = str(item.get("language", ""))
        item_name = item.get("card_name") or ""
        if _normalize(item_name) != target:
            continue

        item_is_foil = str(item.get("foil_flg", "0")) == "1"
        prod_name = (item.get("product_name_en") or item.get("product_name") or "").lower()
        prod_name_has_foil = any(x in prod_name for x in ("foil", "promo", "prerelease", "serial", "galaxy", "retro"))

        # Foil filter
        if foil is True:
            if not item_is_foil:
                continue
        elif foil is False or foil is None:
            if item_is_foil or prod_name_has_foil:
                continue

        # Parse set code and collector number from product_name
        # Format: "【EN】(316)■Showcase■《Sol Ring》[TLE]" or "[LCI-BF]" for borderless foil
        import re as _re
        raw_name = item.get("product_name_en") or item.get("product_name") or ""
        item_num_match = _re.search(r'\((\d+)\)', raw_name)
        item_number = item_num_match.group(1) if item_num_match else None
        # Set code may have suffix like -BF (borderless foil), -EA (extended art) etc
        item_set_match = _re.search(r'\[([A-Z0-9]{2,6})(?:-[A-Z]{1,4})?\]', raw_name)
        item_set_code = item_set_match.group(1).lower() if item_set_match else None

        # Set filter — prefer set code match, fall back to name match
        if set_code:
            if item_set_code and item_set_code != set_code.lower():
                continue
            elif not item_set_code and target_set_name and target_set_name not in prod_name:
                continue

        # Number filter
        if number and item_number and item_number != number:
            continue

        try:
            stock = int(item.get("stock", 0))
        except (TypeError, ValueError):
            stock = 0
        try:
            price_jpy = float(item.get("price", 0))
        except (TypeError, ValueError):
            price_jpy = 0.0

        product_id = item.get("product", "")
        product_url = (
            f"https://www.hareruyamtg.com/en/products/detail/{product_id}?lang=EN"
            if product_id else "https://www.hareruyamtg.com/en/products/search"
        )
        label = (item.get("product_name_en") or item.get("product_name") or item_name).strip()

        if stock > 0 and price_jpy > 0:
            price_aud = round(price_jpy * JPY_TO_AUD, 2)
            entry = (price_aud, label, product_url, int(price_jpy))
            if lang_str == "2":
                en_candidates.append(entry)
            elif lang_str == "1":
                jp_candidates.append(entry)
            else:
                other_candidates.append(entry)
        else:
            if product_id:
                page_lang = "EN" if lang_str == "2" else "JP" if lang_str == "1" else "EN"
                fb = (product_id, label, product_url, page_lang)
                if lang_str == "2":
                    oos_fallback_en.append(fb)
                elif lang_str == "1":
                    oos_fallback_jp.append(fb)
                else:
                    oos_fallback_other.append(fb)

    def resolve(nm_list, oos_list):
        if nm_list:
            return nm_list
        results = []
        for pid, bl, pu, pl in oos_list:
            results.extend(_scrape_conditions_from_page(pid, bl, pu, pl))
        return results

    if language_filter == "EN":
        candidates = resolve(en_candidates, oos_fallback_en)
        return min(candidates, key=lambda x: x[0]) if candidates else (0.0, "Out of stock", "", 0)
    elif language_filter == "EN>JP":
        candidates = resolve(en_candidates, oos_fallback_en)
        if candidates:
            return min(candidates, key=lambda x: x[0])
        jp = resolve(jp_candidates, oos_fallback_jp)
        if jp:
            best = min(jp, key=lambda x: x[0])
            return (best[0], f"[JP] {best[1]}", best[2], best[3])
        return (0.0, "Out of stock", "", 0)
    elif language_filter == "JP":
        candidates = resolve(jp_candidates, oos_fallback_jp)
        return min(candidates, key=lambda x: x[0]) if candidates else (0.0, "Out of stock", "", 0)
    elif language_filter == "Other":
        candidates = resolve(other_candidates, oos_fallback_other)
        return min(candidates, key=lambda x: x[0]) if candidates else (0.0, "Out of stock", "", 0)
    else:
        all_c = resolve(en_candidates, oos_fallback_en) + resolve(jp_candidates, oos_fallback_jp) + resolve(other_candidates, oos_fallback_other)
        return min(all_c, key=lambda x: x[0]) if all_c else (0.0, "Out of stock", "", 0)
