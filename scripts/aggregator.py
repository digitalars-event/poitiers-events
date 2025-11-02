#!/usr/bin/env python3
# coding: utf-8
"""
Agrégateur d'événements Poitiers (avec scraping VisitPoitiers.fr approfondi)
Sources actives :
- OpenAgenda
- Ticketmaster
- Meetup (ICS)
- VisitPoitiers.fr (scraping récursif + suivi “Retrouvez l’agenda”)
"""

import os, sys, json, re, traceback, time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin
import requests
from dateutil import parser as dp
from bs4 import BeautifulSoup
from ics import Calendar
from charset_normalizer import from_bytes

CITY = "Poitiers"
CENTER_LAT = 46.5802
CENTER_LON = 0.3404
RADIUS_KM = 30
TODAY_UTC = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
START_ISO = TODAY_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")

MEETUP_ICS_URLS = [
    "https://www.meetup.com/human-talks-poitiers/events/ical",
    "https://www.meetup.com/fr-FR/afup-poitiers-php/events/ical",
    "https://www.meetup.com/poitiers-aws-user-group/events/ical"
]

TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY", "").strip()
OPENAGENDA_DATASET = "evenements-publics-openagenda"
OPENAGENDA_BASE = "https://public.opendatasoft.com/api/records/1.0/search/"
VISITPOITIERS_BASE = "https://visitpoitiers.fr"


# --- UTILS ---
def parse_date(text) -> Optional[datetime]:
    """Convertit un texte en datetime UTC, ou None."""
    if not text:
        return None
    try:
        dt = dp.parse(str(text), fuzzy=True)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def dedup_key(ev):
    return f"{norm_text(ev.get('title','')).lower()}::{norm_text(ev.get('location','')).lower()}"


def clamp_len(s: str, n: int):
    s = s or ""
    return (s[:n-1] + "…") if len(s) > n else s


def make_event(title, date_start, url, source,
               location=None, date_end=None, description=None):
    """Crée un événement normalisé, et filtre ceux déjà passés."""
    title = clamp_len(norm_text(title), 220)
    if not title:
        return None

    ds = parse_date(date_start)
    if not ds:
        return None

    # 🔥 Filtrage des événements passés
    if ds < TODAY_UTC:
        return None

    return {
        "title": title,
        "date_start": ds.isoformat(),
        "date_end": parse_date(date_end).isoformat() if date_end else None,
        "location": norm_text(location or CITY),
        "link": url or "",
        "source": source,
        "description": norm_text(description or "")
    }


# --- SOURCE 1 : OpenAgenda ---
def fetch_openagenda():
    print("[OpenAgenda] récupération…")
    items = []
    rows, start = 200, 0
    while start < 2000:
        params = {
            "dataset": OPENAGENDA_DATASET,
            "rows": rows,
            "start": start,
            "q": CITY,
            "sort": "firstdate_begin",
        }
        try:
            r = requests.get(OPENAGENDA_BASE, params=params, timeout=25)
            r.raise_for_status()
            for rec in r.json().get("records", []):
                f = rec.get("fields", {})
                title = f.get("title_fr") or f.get("title")
                start_dt = f.get("firstdate_begin") or f.get("start")
                end_dt = f.get("firstdate_end") or f.get("end")
                url = f.get("link") or f.get("url")
                loc = f.get("location_name") or CITY
                e = make_event(title, start_dt, url, "openagenda", loc, end_dt)
                if e:
                    items.append(e)
            start += rows
        except Exception as e:
            print("[OpenAgenda] ERREUR:", e)
            break
    print(f"[OpenAgenda] {len(items)} événements collectés (à venir)")
    return items


# --- SOURCE 2 : Ticketmaster ---
def fetch_ticketmaster():
    print("[Ticketmaster] récupération…")
    if not TICKETMASTER_API_KEY:
        print("[Ticketmaster] Pas de clé API.")
        return []
    items = []
    base = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {"apikey": TICKETMASTER_API_KEY, "city": CITY, "countryCode": "FR"}
    try:
        r = requests.get(base, params=params, timeout=25)
        r.raise_for_status()
        for ev in r.json().get("_embedded", {}).get("events", []):
            title = ev.get("name")
            start = ev.get("dates", {}).get("start", {}).get("dateTime")
            link = ev.get("url")
            loc = CITY
            e = make_event(title, start, link, "ticketmaster", loc)
            if e:
                items.append(e)
    except Exception as e:
        print("[Ticketmaster] ERREUR:", e)
    print(f"[Ticketmaster] {len(items)} événements collectés (à venir)")
    return items


# --- SOURCE 3 : Meetup ICS ---
def fetch_meetup_ics():
    print("[Meetup] récupération…")
    items = []
    for url in MEETUP_ICS_URLS:
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            best = from_bytes(r.content).best()
            text = best.decoded if hasattr(best, "decoded") else str(best)
            cal = Calendar(text)
            for ev in cal.events:
                e = make_event(ev.name, ev.begin.datetime, ev.url, "meetup",
                               ev.location or CITY, ev.end.datetime)
                if e:
                    items.append(e)
        except Exception as e:
            print(f"[Meetup ICS] ERREUR sur {url} :", e)
    print(f"[Meetup] {len(items)} événements collectés (à venir)")
    return items

# --- SOURCE 4 : VisitPoitiers ---
def fetch_visitpoitiers():
    print("[VisitPoitiers] Scraping pages d’activités…")
    base = VISITPOITIERS_BASE
    visited, events = set(), []
    start_url = f"{base}/activites/"
    
    try:
        r = requests.get(start_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 1️⃣ Trouver tous les liens vers /activite/xxxx/
        activity_links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"/activite/[^/]+/?$", href):
                activity_links.add(urljoin(base, href))

        print(f" - {len(activity_links)} pages d’activités détectées.")

        # 2️⃣ Parcourir chaque page /activite/
        for link in activity_links:
            if link in visited:
                continue
            visited.add(link)
            time.sleep(0.4)
            try:
                r2 = requests.get(link, timeout=15)
                if "text/html" not in r2.headers.get("Content-Type", ""):
                    continue
                soup2 = BeautifulSoup(r2.text, "html.parser")

                # Nom principal de la page (souvent h1)
                title_tag = soup2.find(["h1", "h2"])
                title = title_tag.get_text(strip=True) if title_tag else link.split("/")[-2].replace("-", " ").title()

                # Extraire description courte
                desc_tag = soup2.find("p")
                desc = desc_tag.get_text(strip=True) if desc_tag else ""

                # Créer un "événement" de type "établissement"
                ev = {
                    "title": title,
                    "date_start": START_ISO,  # non daté, mais on met la date du jour
                    "location": "Poitiers",
                    "link": link,
                    "source": "visitpoitiers",
                    "description": desc
                }
                events.append(ev)

                # 3️⃣ Chercher des liens vers agendas externes
                for a2 in soup2.find_all("a", href=True):
                    href2 = a2["href"]
                    if any(k in href2.lower() for k in [
                        "agenda", "event", "evenement", "calendrier", "openagenda",
                        "facebook.com/events", "google.com/calendar"
                    ]):
                        full_link = urljoin(link, href2)
                        if full_link not in visited:
                            visited.add(full_link)
                            print(f"   ↳ Agenda trouvé : {full_link}")
                            # Ajouter comme “source découverte”
                            events.append({
                                "title": f"Agenda lié à {title}",
                                "date_start": START_ISO,
                                "location": "Poitiers",
                                "link": full_link,
                                "source": "visitpoitiers-agenda",
                                "description": "Lien externe vers un calendrier ou agenda."
                            })

            except Exception as e:
                print(f"[VisitPoitiers] Erreur sur {link}: {e}")

    except Exception as e:
        print("[VisitPoitiers] ERREUR racine:", e)

    print(f"[VisitPoitiers] {len(events)} pages collectées (activités + agendas externes)")
    return events



# --- MAIN ---
def main():
    all_items = []
    all_items += fetch_openagenda()
    all_items += fetch_ticketmaster()
    all_items += fetch_meetup_ics()
    all_items += fetch_visitpoitiers()

    dedup, seen = [], set()
    for e in all_items:
        k = dedup_key(e)
        if k not in seen:
            seen.add(k)
            dedup.append(e)

    dedup.sort(key=lambda e: parse_date(e["date_start"]) or TODAY_UTC)
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "events": dedup},
                  f, ensure_ascii=False, indent=2)
    print(f"\n✅ {len(dedup)} événements écrits dans events.json (futurs uniquement)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
