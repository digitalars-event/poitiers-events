import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json

def scrape_arena():
    url = "https://www.arena-futuroscope.com/la-programmation/"
    print(f"🎤 Scraping {url} ...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"❌ Erreur HTTP {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    events = []

    cards = soup.select("div.card.main-card")
    print(f"✅ {len(cards)} événements trouvés")

    for card in cards:
        try:
            title = card.select_one(".card__title")
            title = title.get_text(strip=True) if title else "Sans titre"

            # Date et heure
            meta = card.select_one(".card__meta")
            date_text = meta.get_text(strip=True) if meta else ""
            date_iso = None
            if meta and "datetime" in card.select_one("time", default={}).attrs:
                date_iso = card.select_one("time")["datetime"]
            else:
                # Tentative de parsing manuel
                try:
                    date_iso = datetime.strptime(date_text.split("-")[0].strip(), "%d %B %Y").isoformat()
                except Exception:
                    date_iso = None

            # Image
            img_tag = card.select_one(".card__block-image img")
            img = img_tag["src"] if img_tag else None

            # Lien “plus d’infos”
            info_link = card.select_one("a.stretch-link")
            info_link = info_link["href"] if info_link else None

            # Lien “réserver”
            reserve_btn = card.select_one("a.btn-resa-meeting, a.btn-resa-manifestation")
            reserve_link = reserve_btn["href"] if reserve_btn else None

            events.append({
                "title": title,
                "date": date_text,
                "release": date_iso,
                "poster": img,
                "cinema": "Arena Futuroscope",
                "source": info_link,
                "reservation": reserve_link,
                "scraped_at": datetime.now().isoformat()
            })

        except Exception as e:
            print(f"⚠️ Erreur sur une carte : {e}")

    # Sauvegarde JSON
    output = {"events": events}
    with open("events_arena.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"💾 {len(events)} événements sauvegardés dans events_arena.json")
    return events

if __name__ == "__main__":
    scrape_arena()

