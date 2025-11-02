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
    print("[VisitPoitiers] Scraping complet…")
    base = VISITPOITIERS_BASE
    visited, events = set(), []
    start_urls = [f"{base}/activites/", f"{base}/agenda/"]

    def crawl(url, depth=0, max_depth=3):
        if url in visited or depth > max_depth:
            return
        visited.add(url)
        try:
            r = requests.get(url, timeout=10)
            if "text/html" not in r.headers.get("Content-Type", ""):
                return
            soup = BeautifulSoup(r.text, "html.parser")

            # Bouton "agenda" (toutes variantes)
            for link in soup.find_all("a", string=re.compile("agenda", re.I)):
                next_url = urljoin(url, link["href"])
                crawl(next_url, depth + 1, max_depth)

            # Liens vers pages d’activités
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r"/activite[s]?/", href) and base in urljoin(url, href):
                    crawl(urljoin(url, href), depth + 1, max_depth)

            # Extraction d’événements (titres + dates)
            for h in soup.find_all(["h2", "h3", "h1"]):
                if any(k in h.get_text().lower() for k in ["concert", "expo", "spectacle", "atelier", "balade"]):
                    date = None
                    for p in h.find_all_next("p", limit=5):
                        if re.search(r"\b20\d{2}\b", p.text):
                            date = p.text.strip()
                            break
                    ev = make_event(h.get_text(), date or START_ISO, url, "visitpoitiers",
                                    location="Poitiers")
                    if ev:
                        events.append(ev)
        except Exception as e:
            print(f"[VisitPoitiers] Erreur sur {url}: {e}")
        time.sleep(0.2)

    for u in start_urls:
        crawl(u)
    print(f"[VisitPoitiers] {len(events)} événements collectés (à venir)")
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
