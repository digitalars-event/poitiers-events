# scrapers/cgr.py
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

def scrape():
    """Scraper spécialisé pour le Méga CGR Buxerolles."""
    url = "https://www.cgrcinemas.fr/buxerolles/films-a-l-affiche/"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    events = []
    for film in soup.select(".film-item"):
        title = film.select_one(".film-title")
        img = film.select_one("img")
        desc = film.select_one(".film-synopsis")

        events.append({
            "title": title.get_text(strip=True) if title else "Film CGR",
            "description": desc.get_text(strip=True) if desc else "",
            "link": url,
            "image": img["src"] if img else "",
            "source": "cgrcinemas.fr",
            "date_start": datetime.now(timezone.utc).isoformat()
        })
    return events

