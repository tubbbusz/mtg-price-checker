import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from .gg import _extract_base_name


def _parse_shuffled_title(title: str):
    """
    Parse Shuffled title: "Card Name (SET-NUM) - Set Name [Foil]"
    Returns (card_base, set_code, number, is_foil)
    """
    is_foil = bool(re.search(r'\bfoil\b', title, re.I))

    # Extract (SET-NUM) — last parenthetical with SET-NUM format
    # Handles: (SLD-744), (2XM-372), (UNF-209B), (LIST-MRD-266) -> use last segment
    paren_match = re.search(r'\(([A-Z0-9]+-[A-Z0-9]+(?:-[A-Z0-9]+)*)\)', title)
    set_code = None
    number = None
    if paren_match:
        parts = paren_match.group(1).split('-')
        # LIST-MRD-266 -> set=MRD, num=266; SLD-744 -> set=SLD, num=744
        if len(parts) >= 3 and parts[0] == 'LIST':
            set_code = parts[1]
            number = parts[2]
        else:
            set_code = parts[0]
            number = parts[1] if len(parts) > 1 else None

    # Card base name: everything before first ( or after last ) strip
    base = title
    base = re.sub(r'\s*\([^)]*\)', '', base)   # remove parentheticals
    base = base.split(' - ')[0].strip()          # remove " - Set Name" suffix
    base = _extract_base_name(base)

    return base, set_code, number, is_foil


def scrape_shuffled(card_name: str, set_code=None, number=None, foil=None):
    target = _extract_base_name(card_name)
    url = f"https://shuffled.com.au/search?page=1&q=%2A{quote_plus(card_name)}%2A"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for card in soup.select("div.productCard__card"):
            title_tag = card.select_one("p.productCard__title a")
            if not title_tag:
                continue

            full_title = title_tag.get_text(strip=True)
            card_base, card_set, card_num, card_foil = _parse_shuffled_title(full_title)

            if card_base != target:
                continue

            # Set filter
            if set_code and card_set and card_set.lower() != set_code.lower():
                continue

            # Number filter
            if number and card_num and card_num.lstrip('0') != number.lstrip('0'):
                continue

            # Foil filter
            if foil is True and not card_foil:
                continue
            if foil is False and card_foil:
                continue

            href = title_tag.get("href", "").split("?")[0]
            link = "https://shuffled.com.au" + href if href.startswith("/") else href

            # Find cheapest available NM chip
            for chip in card.select("li.productChip"):
                if chip.get("data-variantavailable") != "true":
                    continue
                qty = int(chip.get("data-variantqty", "0") or 0)
                if qty <= 0:
                    continue
                vtitle = chip.get("data-varianttitle", "").lower()
                if "near mint" not in vtitle:
                    continue
                try:
                    price = int(chip.get("data-variantprice", "0") or 0) / 100
                except (ValueError, TypeError):
                    continue
                if price > 0:
                    vid = chip.get("data-variantid", "")
                    vurl = f"{link}?variant={vid}" if vid else link
                    results.append((price, full_title, vurl))
                    break  # only need NM

        if not results:
            return (0.0, "Out of stock", "")
        return min(results, key=lambda x: x[0])
    except Exception:
        return (0.0, "Error", "")
