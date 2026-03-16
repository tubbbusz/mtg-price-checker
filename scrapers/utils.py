import re


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[''\":,?!()\[\]{}]", "", text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    text = text.split("(")[0].split("[")[0].strip()
    return text


def parse_card_query(query: str):
    query = query.strip()
    foil = "*F*" in query
    etched = "*E*" in query
    query = query.replace("*F*", "").replace("*E*", "").strip()

    set_code = None
    number = None

    set_match = re.search(r"\(([a-z0-9]+)\)", query, re.IGNORECASE)
    if set_match:
        set_code = set_match.group(1).upper()
        query = query.replace(set_match.group(0), "").strip()

    id_match = re.search(r"([A-Z0-9]+)-(\d+[a-z]*)", query, re.IGNORECASE)
    if id_match:
        set_code = id_match.group(1).upper()
        number = id_match.group(2)
        query = query.replace(id_match.group(0), "").strip()
    else:
        num_match = re.search(r"(\d+[a-z]*)$", query, re.IGNORECASE)
        if num_match:
            number = num_match.group(1)
            query = query[: num_match.start()].strip()

    return query.strip(), set_code, number, foil, etched
