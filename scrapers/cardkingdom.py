import json
import os
import traceback

_last_error = ""
_PRICES_FILE = os.path.join(os.path.dirname(__file__), "ck_prices.json")


def load_ck_prices() -> dict:
    global _last_error
    try:
        if not os.path.exists(_PRICES_FILE):
            _last_error = "ck_prices.json not found - run build_ck_prices.py locally"
            print(f"[CK] {_last_error}")
            return {}

        with open(_PRICES_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)

        print(f"[CK] Loaded {len(cache)} prices from local file")
        _last_error = ""
        return cache

    except Exception as e:
        _last_error = f"{type(e).__name__}: {e}"
        print(f"[CK] Failed: {_last_error}")
        traceback.print_exc()
        return {}


def get_ck_price(card_name: str, cache: dict) -> float | None:
    return cache.get(card_name.strip().lower()) if cache else None


def get_last_error() -> str:
    return _last_error
