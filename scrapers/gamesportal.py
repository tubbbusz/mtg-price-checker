from .gg import scrape_gg


def scrape_gamesportal(card_name: str, set_code=None, number=None, foil=None):
    return scrape_gg(card_name, "https://gamesportal.com.au", set_code, number, foil)
