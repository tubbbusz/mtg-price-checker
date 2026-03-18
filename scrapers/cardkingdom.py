import gzip
import json
import requests
import traceback

_last_error = ""


def load_ck_prices() -> dict:
    global _last_error
    headers = {"User-Agent": "ScrappingMyAss/1.0"}

    # Try CK CSV first (tiny file, name-keyed)
    try:
        print("[CK] Trying CK price CSV...")
        import io, csv
        r = requests.get(
            "https://www.cardkingdom.com/export/price",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        print(f"[CK] CSV HTTP {r.status_code} size={len(r.content)}b preview={r.text[:300]!r}")
        r.raise_for_status()
        cache = {}
        reader = csv.DictReader(io.StringIO(r.text))
        print(f"[CK] CSV headers: {reader.fieldnames}")
        for row in reader:
            foil = row.get("Foil", "").strip().upper() in ("YES", "Y", "TRUE", "1")
            if foil:
                continue
            name = (row.get("Name") or "").strip().lower()
            price_str = (row.get("Retail Price") or row.get("Buy Price") or
                        row.get("Price") or row.get("price_retail") or "0")
            try:
                price = float(str(price_str).replace("$","").strip() or 0)
            except ValueError:
                continue
            if name and price > 0:
                if name not in cache or price < cache[name]:
                    cache[name] = price
        if cache:
            print(f"[CK] CSV success: {len(cache)} cards")
            _last_error = ""
            return cache
        print(f"[CK] CSV empty after parse")
    except Exception as e:
        print(f"[CK] CSV failed: {e}")

    # MTGJSON: stream and parse AllPricesToday only — log a sample entry
    # to find what keys are available for name lookup
    try:
        print("[CK] Downloading AllPricesToday to inspect structure...")
        r2 = requests.get(
            "https://mtgjson.com/api/v5/AllPricesToday.json.gz",
            headers=headers, timeout=60, stream=True,
        )
        r2.raise_for_status()
        prices_data = json.loads(gzip.decompress(r2.content)).get("data", {})
        print(f"[CK] AllPricesToday: {len(prices_data)} UUIDs")

        # Log first 3 entries completely to understand structure
        for i, (uuid, block) in enumerate(prices_data.items()):
            if i >= 3:
                break
            print(f"[CK] Entry {i}: uuid={uuid} keys={list(block.keys())} block={json.dumps(block)[:400]}")

    except Exception as e:
        print(f"[CK] AllPricesToday inspect failed: {e}")

    _last_error = "Could not load CK prices"
    return {}


def get_ck_price(card_name: str, cache: dict) -> float | None:
    return cache.get(card_name.strip().lower()) if cache else None


def get_last_error() -> str:
    return _last_error