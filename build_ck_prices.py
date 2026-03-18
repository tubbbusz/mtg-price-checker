"""
Run this script once locally to generate scrapers/ck_prices.json
Place AllPricesToday.json.gz and AllIdentifiers.json.gz in the same folder as this script.
"""
import gzip, json

print("Loading AllIdentifiers...")
with gzip.open("AllIdentifiers.json.gz", "rb") as f:
    all_ids = json.load(f).get("data", {})
print(f"  {len(all_ids)} entries")

# Build uuid -> name
uuid_to_name = {}
for uuid, card in all_ids.items():
    name = card.get("name", "").strip()
    if name:
        uuid_to_name[uuid] = name
del all_ids
print(f"  UUID->name map: {len(uuid_to_name)}")

print("Loading AllPricesToday...")
with gzip.open("AllPricesToday.json.gz", "rb") as f:
    prices = json.load(f).get("data", {})
print(f"  {len(prices)} UUIDs")

cache = {}
for uuid, block in prices.items():
    name = uuid_to_name.get(uuid, "").strip().lower()
    if not name:
        continue
    try:
        ck = (block.get("paper", {})
                   .get("cardkingdom", {})
                   .get("retail", {})
                   .get("normal", {}))
        if not ck:
            continue
        price = float(list(ck.values())[-1])
        if price > 0:
            if name not in cache or price < cache[name]:
                cache[name] = price
    except (TypeError, ValueError, AttributeError, IndexError):
        continue

print(f"Cache: {len(cache)} cards")

out_path = "scrapers/ck_prices.json"
with open(out_path, "w") as f:
    json.dump(cache, f)

import os
size_kb = os.path.getsize(out_path) // 1024
print(f"Written to {out_path} ({size_kb} KB)")
