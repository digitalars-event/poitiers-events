#!/usr/bin/env python3
# coding: utf-8

import requests
from bs4 import BeautifulSoup
from datetime import datetime

BASE_URL = "https://republic-corner.fr/espace-republic-corner/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def get_event_details(ticket_url):
    """
    Récupère les informations depuis la page billetterie (titre, date, description).
    Fonctionne avec Shotgun, Weezevent ou FnacSpectacles.
    """
    try:
        res = requests.get(ticket_url, headers=HEADERS, timeout=20)
        if res.status_code != 200:
            return {}

        soup = BeautifulSoup(res.text, "html.parser")

        # --- Shotgun ---
        if "shotgun.live" in ticket_url:
            title = soup.find("h1")
            date = soup.find("time")
            desc = soup.find("meta", {"name": "description"})
            return {
                "title": title.get_text(strip=True) if title else None,
                "date": date.get_text(strip=True) if date else None,
                "description": desc["content"] if desc else None,
            }

        # --- Weezevent ---
        if "weezevent.com" in ticket_url:
            title = soup.find("h1")
            desc = soup.find("meta", {"name": "description"})
            date = None
            # Recherche d'une date dans le texte
            for t in soup.find_all(text=True):
                if any(mois in t.lower() for mois in ["janvier", "février", "mars", "avril", "mai", "juin",
                                                      "juillet", "août", "septembre", "octobre", "novembre", "décembre"]):
                    date = t.strip()
                    break
            return {
                "title": title.get_text(strip=True) if title else None,
                "date": date,
                "description": desc["content"] if desc else None,
            }

        # --- FnacSpectacles ---
        if "fnacspectacles.com" in ticket_url:
            title = soup.find("h1")
            desc = soup.find("meta", {"name": "description"})
            date = None
            for t in soup.find_all(text=True):
                if any(mois in t.lower() for mois in ["janvier", "février", "mars", "avril", "mai", "juin",
                                                      "juillet", "août", "septembre", "octobre", "novembre", "décembre"]):
                    date = t.strip()
                    break
            return {
                "title": title.get_text(strip=True) if title else None,
                "date": date,
                "description": desc["content"] if desc else None,
            }

        return {}
    except Exception as e:
        print(f"⚠️ Erreur récupération détail {ticket_url}: {e}")
        return {}


def scrape_republic_corner():
    print("🎭 Republic Corner...")
    res = requests.get(BASE_URL, headers=HEADERS, timeout=30)
    if res.status_code != 200:
        print(f"❌ Erreur de chargement ({res.status_code})")
        return []

    soup = BeautifulSoup(res.text, "html.parser")

    # Chaque événement est une colonne contenant une image et un bouton "Billetterie"
    events = []
    for col in soup.select(".et_pb_column"):
        img_tag = col.select_one("img")
        btn_tag = col.select_one("a.et_pb_button")

        if not img_tag or not btn_tag:
            continue

        poster = img_tag.get("src")
        ticket_link = btn_tag.get("href")

        # On suit le lien pour récupérer les infos
        details = get_event_details(ticket_link)
        title = details.get("title") or "Événement"
        date = details.get("date")
        description = details.get("description")

        event = {
            "title": title.strip(),
            "date": date.strip() if date else None,
            "description": description,
            "poster": poster,
            "cinema": "Republic Corner",
            "source": ticket_link,
            "scraped_at": datetime.now().isoformat()
        }

        events.append(event)

    print(f"✅ {len(events)} événements récupérés depuis Republic Corner.")
    return events


if __name__ == "__main__":
    data = scrape_republic_corner()
    print(f"💾 {len(data)} événements trouvés.")
    for e in data[:5]:
        print(f"- {e['title']} ({e['source']})")
