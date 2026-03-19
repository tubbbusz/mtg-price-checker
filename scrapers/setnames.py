"""
Provides a set code -> full set name lookup.
Fetches from Scryfall sets API on first use and caches in memory.
Falls back to an empty dict if unavailable.
"""
import requests
import threading

_cache: dict = {}  # code.lower() -> full name
_loaded = False
_lock = threading.Lock()


def _load():
    global _cache, _loaded
    try:
        r = requests.get(
            "https://api.scryfall.com/sets",
            headers={"User-Agent": "ScrappingMyAss/1.0"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        with _lock:
            for s in data:
                code = s.get("code", "").lower()
                name = s.get("name", "")
                if code and name:
                    _cache[code] = name
            _loaded = True
        print(f"[SetNames] Loaded {len(_cache)} set names from Scryfall")
    except Exception as e:
        print(f"[SetNames] Failed to load: {e}")
        with _lock:
            _loaded = True  # don't retry


def get_set_name(code: str) -> str:
    """Return full set name for a set code, or empty string if unknown."""
    global _loaded
    if not _loaded:
        _load()
    return _cache.get(code.lower(), "")


# Load in background at import time
threading.Thread(target=_load, daemon=True).start()
