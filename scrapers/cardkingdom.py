import gzip
import json
import requests
import traceback

_last_error = ""


def load_ck_prices() -> dict:
    global _last_error
    headers = {"User-Agent": "ScrappingMyAss/1.0"}

    try:
        # AtomicCards is name -> list of printings, each printing has identifiers
        print("[CK] Downloading AtomicCards...")
        r1 = requests.get(
            "https://mtgjson.com/api/v5/AtomicCards.json.gz",
            headers=headers, timeout=60, stream=True,
        )
        r1.raise_for_status()
        atomic = json.loads(gzip.decompress(r1.content)).get("data", {})
        print(f"[CK] AtomicCards: {len(atomic)} entries")

        # Debug: inspect structure of first entry
        if atomic:
            sample_name = next(iter(atomic))
            sample_val = atomic[sample_name]
            print(f"[CK] Sample key={sample_name!r} type={type(sample_val).__name__}")
            if isinstance(sample_val, list) and sample_val:
                print(f"[CK] Sample[0] keys: {list(sample_val[0].keys())[:10]}")
                print(f"[CK] Sample[0] identifiers: {sample_val[0].get('identifiers', 'MISSING')}")
            elif isinstance(sample_val, dict):
                print(f"[CK] Sample keys: {list(sample_val.keys())[:10]}")
                print(f"[CK] Sample identifiers: {sample_val.get('identifiers', 'MISSING')}")

        # Build uuid -> name — AtomicCards format: {name: [face_obj, ...]}
        # Each face_obj has identifiers.mtgjsonId BUT AtomicCards uses
        # oracle-level data so may not have per-printing UUIDs.
        # Instead use identifiers.scryfallOracleId or mtgjsonFoilId/mtgjsonNonFoilId
        uuid_to_name = {}
        for name, val in atomic.items():
            faces = val if isinstance(val, list) else [val]
            for face in faces:
                ids = face.get("identifiers", {})
                # Try all UUID-like fields
                for field in ("mtgjsonId", "mtgjsonFoilId", "mtgjsonNonFoilId"):
                    uid = ids.get(field)
                    if uid:
                        uuid_to_name[uid] = name

        print(f"[CK] UUID map: {len(uuid_to_name)} entries")

        # If still 0, AtomicCards doesn't have per-printing UUIDs
        # Fall back: use AllIdentifiers which IS per-printing UUID keyed
        if not uuid_to_name:
            print("[CK] AtomicCards has no UUIDs, trying AllIdentifiers...")
            r_ids = requests.get(
                "https://mtgjson.com/api/v5/AllIdentifiers.json.gz",
                headers=headers, timeout=90, stream=True,
            )
            r_ids.raise_for_status()
            all_ids = json.loads(gzip.decompress(r_ids.content)).get("data", {})
            print(f"[CK] AllIdentifiers: {len(all_ids)} UUIDs")
            for uuid, card in all_ids.items():
                name = card.get("name", "").strip()
                if name:
                    uuid_to_name[uuid] = name
            print(f"[CK] UUID map built: {len(uuid_to_name)} entries")

        # AllPricesToday
        print("[CK] Downloading AllPricesToday...")
        r2 = requests.get(
            "https://mtgjson.com/api/v5/AllPricesToday.json.gz",
            headers=headers, timeout=60, stream=True,
        )
        r2.raise_for_status()
        prices_data = json.loads(gzip.decompress(r2.content)).get("data", {})
        print(f"[CK] AllPricesToday: {len(prices_data)} UUIDs")

        cache = {}
        matched = 0
        for uuid, price_block in prices_data.items():
            name = uuid_to_name.get(uuid, "").strip().lower()
            if not name:
                continue
            matched += 1
            try:
                ck_retail = (
                    price_block.get("paper", {})
                    .get("cardkingdom", {})
                    .get("retail", {})
                    .get("normal", {})
                )
                if not ck_retail:
                    continue
                price = float(list(ck_retail.values())[-1])
            except (TypeError, ValueError, AttributeError, IndexError):
                continue
            if price <= 0:
                continue
            if name not in cache or price < cache[name]:
                cache[name] = price

        print(f"[CK] UUID matches: {matched} | Price cache: {len(cache)} cards")
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
