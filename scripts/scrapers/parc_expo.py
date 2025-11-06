#!/usr/bin/env python3
# coding: utf-8

import requests
from bs4 import BeautifulSoup
from datetime import datetime

BASE_URL = "https://www.parcexpo-grandpoitiers.fr/les-prochains-evenements/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def scrape_parc_expo():
    print("🏛️ Parc Expo Grand Poitiers...")
    res = requests.get(BASE_URL, headers=HEADERS, timeout=30)
    if res.status_code != 200:
        print(f"❌ Erreur de chargement ({res.status_code})")
        return []

    soup = BeautifulSoup(res.text, "html.parser")

    events = []
    cards = soup.select(".event-item, .wp-block-columns, article")  # tolérance large
    if not cards:
        print("⚠️ Aucun événement détecté sur la page.")
        return []

    for card in cards:
        try:
            # 🔗 Lien de redirection
            link_tag = card.find("a", href=True)
            link = link_tag["href"] if link_tag else None
            if link and not link.startswith("http"):
                link = "https://www.parcexpo-grandpoitiers.fr" + link

            # 🖼️ Image
            img_tag = card.find("img")
            poster = img_tag["src"] if img_tag else None

            # 🗓️ Date
            date_tag = card.find(class_="event-date") or card.find("time")
            date = date_tag.get_text(strip=True) if date_tag else None

            # 🎫 Nom de l'événement
            title_tag = card.find("h2") or card.find("h3") or card.find("strong")
            title = title_tag.get_text(strip=True) if title_tag else None

            # Vérifie qu’on a un minimum d’infos
            if not title and not poster:
                continue

            event = {
                "title": title or "Événement",
                "date": date,
                "poster": poster,
                "cinema": "Parc Expo Grand Poitiers",
                "source": link,
                "scraped_at": datetime.now().isoformat(),
            }

            events.append(event)
        except Exception as e:
            print(f"⚠️ Erreur sur un bloc événement : {e}")
            continue

    print(f"✅ {len(events)} événements récupérés depuis le Parc Expo.")
    return events


if __name__ == "__main__":
    data = scrape_parc_expo()
    print(f"💾 {len(data)} événements trouvés.")
    for e in data[:5]:
        print(f"- {e['title']} ({e['date']}) → {e['source']}")
