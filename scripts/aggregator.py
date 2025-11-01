#!/usr/bin/env python3
# coding: utf-8
"""
Agrégateur d'événements Poitiers (avec scraping approfondi VisitPoitiers.fr)
Sources actives :
- OpenAgenda via OpenData (dataset 'evenements-publics-openagenda')
- Ticketmaster Discovery API (clé: TICKETMASTER_API_KEY)
- Meetup (flux ICS)
- VisitPoitiers.fr (scraping récursif avec suivi de l’agenda)
"""

import os, sys, json, re, traceback, time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
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
TODAY_UTC = datetime.now(timezone.utc)
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


# --- UTILITAIRES ---
def parse_date(iso_or_text) -> Optional[datetime]:
    if not iso_or_text:
        return None
    try:
        dt = dp.parse(iso_or_text, fuzzy=True)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def dedup_key(ev: Dict[str, Any]) -> str:
    return f"{norm_text(ev.get('title', '')).lower()}::{norm_text(ev.get('location', '')).lower()}"


def clamp_len(s: str, n: int) -> str:
    s = s or ""
    return (s[:n-1] + "…") if len(s) > n else s


def make_event(title, date_start, url, source,
               location=None, date_end=None, description=None):
    title = clamp_len(norm_text(title), 220)
    if not title:
        return None
    ds = parse_date(date_start) if date_start else None
    if not ds or ds < TODAY_UTC:
        return None
    return {
        "title": title,
        "date_start": ds.isoformat(),
        "date_end": parse_date(date_end).isoformat() if date_end else None,
        "location": norm_text(location) if location else CITY,
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
            recs = r.json().get("records", [])
            if not recs:
                break
            for rec in recs:
                f = rec.get("fields", {}) or {}
                title = f.get("title_fr") or f.get("title") or ""
                start_dt = f.get("firstdate_begin") or f.get("start")
                end_dt = f.get("firstdate_end") or f.get("end")
                url = f.get("link") or f.get("url") or ""
                loc = f.get("location_name") or f.get("city") or CITY
                ev = make_event(title, start_dt, url, "openagenda", loc, end_dt)
                if ev:
                    items.append(ev)
            start += rows
        except Exception as e:
            print("[OpenAgenda] ERREUR:", e)
            break
    print(f"[OpenAgenda] {len(items)} événements collectés")
    return items


# --- SOURCE 2 : Ticketmaster ---
def fetch_ticketmaster():
    print("[Ticketmaster] récupération…")
    if not TICKETMASTER_API_KEY:
        print("[Ticketmaster] Pas de clé API, source ignorée")
        return []
    items = []
    base = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        "apikey": TICKETMASTER_API_KEY,
        "countryCode": "FR",
        "city": CITY,
        "startDateTime": START_ISO,
        "size": "100"
    }
    try:
        r = requests.get(base, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        for ev in data.get("_embedded", {}).get("events", []):
            title = ev.get("name", "")
            start = (ev.get("dates", {}).get("start") or {}).get("dateTime")
            link = ev.get("url", "")
            loc_name = CITY
            venues = (ev.get("_embedded", {}) or {}).get("venues", [])
            if venues:
                loc_name = venues[0].get("name") or CITY
            e = make_event(title, start, link, "ticketmaster", loc_name)
            if e:
                items.append(e)
    except Exception as e:
        print("[Ticketmaster] ERREUR:", e)
    print(f"[Ticketmaster] {len(items)} événements collectés")
    return items


# --- SOURCE 3 : Meetup ICS ---
def fetch_meetup_ics():
    print("[Meetup] récupération…")
    items = []
    for url in MEETUP_ICS_URLS:
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            text = from_bytes(r.content).best().output_text
            cal = Calendar(text)
            for ev in cal.events:
                title = ev.name or ""
                start = ev.begin.datetime if ev.begin else None
                end = ev.end.datetime if ev.end else None
                loc = ev.location or CITY
                link = ev.url or ""
                e = make_event(title, start, link, "meetup", loc, end)
                if e:
                    items.append(e)
        except Exception as e:
            print(f"[Meetup ICS] ERREUR sur {url} :", e)
    print(f"[Meetup] {len(items)} événements collectés")
    return items


# --- SOURCE 4 : VisitPoitiers.fr ---
def fetch_visitpoitiers():
    print("[VisitPoitiers] Scraping complet…")
    base = VISITPOITIERS_BASE
    start_urls = [f"{base}/activites/", f"{base}/agenda/"]
    visited, events = set(), []

    def crawl(url, depth=0, max_depth=4):
        if url in visited or depth > max_depth:
            return
        visited.add(url)
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                return
            soup = BeautifulSoup(r.text, "html.parser")

            # Si bouton "Retrouvez l'agenda" → suivre ce lien
            for link in soup.find_all("a", string=re.compile("Retrouvez l.agenda", re.I)):
                next_url = urljoin(url, link["href"])
                crawl(next_url, depth + 1, max_depth)

            # Détection d'événements sur la page
            for block in soup.find_all(["article", "div"], class_=re.compile("event|agenda|sortie", re.I)):
                title = block.find(["h2", "h3"])
                if not title:
                    continue
                title = title.get_text(strip=True)
                desc = block.find("p")
                desc = desc.get_text(strip=True) if desc else ""
                date_text = None
                for tag in block.find_all("p"):
                    if re.search(r"\b20\d{2}\b", tag.get_text()):
                        date_text = tag.get_text(strip=True)
                        break
                ev = make_event(title, date_text or START_ISO, url, "visitpoitiers",
                                location="Poitiers", description=desc)
                if ev:
                    events.append(ev)

            # Suivre les liens internes
            for link in soup.find_all("a", href=True):
                next_url = urljoin(url, link["href"])
                if base in next_url and next_url not in visited:
                    crawl(next_url, depth + 1, max_depth)

        except Exception as e:
            print(f"[VisitPoitiers] Erreur sur {url}: {e}")
        time.sleep(0.3)

    for start_url in start_urls:
        crawl(start_url)
    print(f"[VisitPoitiers] {len(events)} événements collectés")
    return events


# --- MAIN ---
def main():
    all_items = []
    all_items += fetch_openagenda()
    all_items += fetch_ticketmaster()
    all_items += fetch_meetup_ics()
    all_items += fetch_visitpoitiers()

    seen, dedup = set(), []
    for ev in all_items:
        k = dedup_key(ev)
        if k not in seen:
            seen.add(k)
            dedup.append(ev)

    dedup.sort(key=lambda e: parse_date(e["date_start"]) or TODAY_UTC)

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "events": dedup},
                  f, ensure_ascii=False, indent=2)

    print(f"\n✅ {len(dedup)} événements écrits dans events.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
