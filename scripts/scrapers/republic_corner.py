#!/usr/bin/env python3
# coding: utf-8

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import re

BASE_URL = "https://republic-corner.fr/espace-republic-corner/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def get_event_details(ticket_url):
    """Récupère les informations depuis la page billetterie (Shotgun, Weezevent, Fnac...)."""
    try:
        res = requests.get(ticket_url, headers=HEADERS, timeout=30)
        if res.status_code != 200:
            return {}

        soup = BeautifulSoup(res.text, "html.parser")

        # --- SHOTGUN ---
        if "shotgun.live" in ticket_url:
            # Extraire le JSON-LD contenant les infos de l'événement
            ld_json = soup.find("script", type="application/ld+json")
            if ld_json:
                data = json.loads(ld_json.string)
                title = data.get("name")
                date = data.get("startDate")
                image = data.get("image")
                address = (
                    data.get("location", {})
                    .get("address", {})
                    .get("streetAddress", "Espace Republic Corner, Poitiers")
                )
                desc = soup.find("meta", {"name": "description"})
                return {
                    "title": title,
                    "date": date,
                    "description": desc["content"] if desc else None,
                    "address": address,
                    "poster": image,
                }

        # --- WEEZEVENT ---
        if "weezevent.com" in ticket_url:
            title = soup.select_one(".gemino-data-event-title")
            date = soup.select_one(".gemino-data-event-date")
            desc = soup.find("meta", {"name": "description"})
            image = soup.select_one("#gemino-img-banner")
            return {
                "title": title.get_text(strip=True) if title else None,
                "date": date.get_text(strip=True) if date else None,
                "description": desc["content"] if desc else None,
                "poster": image["src"] if image else None,
                "address": "Espace Republic Corner, Poitiers",
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
    events = []

    # Chaque événement est une colonne contenant une image et un bouton Billetterie
    for col in soup.select(".et_pb_column"):
        img_tag = col.select_one("img")
        btn_tag = col.select_one("a.et_pb_button")

        if not img_tag or not btn_tag:
            continue

        poster = img_tag.get("src")
        ticket_link = btn_tag.get("href")

        # Détails via page billetterie
        details = get_event_details(ticket_link)
        title = details.get("title") or "Événement Republic Corner"
        date = details.get("date")
        description = details.get("description")
        address = details.get("address", "Espace Republic Corner, Poitiers")

        event = {
            "title": title.strip(),
            "date": date.strip() if isinstance(date, str) else date,
            "description": description,
            "poster": details.get("poster") or poster,
            "address": address,
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
