#!/usr/bin/env python3
# coding: utf-8
"""
Agrégateur d'événements Poitiers (avec scraping VisitPoitiers.fr)
Sources actives :
- OpenAgenda via OpenData (dataset 'evenements-publics-openagenda')
- Ticketmaster Discovery API (clé: TICKETMASTER_API_KEY)
- Meetup (flux ICS)
- VisitPoitiers.fr (scraping complet récursif)
"""

import os, sys, json, math, re, traceback, time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

import requests
from dateutil import parser as dp
from bs4 import BeautifulSoup
from ics import Calendar
from charset_normalizer import from_bytes

# --- PARAMÈTRES GÉNÉRAUX ---
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

# --- OUTILS GÉNÉRIQUES ---
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    from math import radians, sin, cos, asin, sqrt
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = phi2 - phi1
    dl = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dl/2)**2
    return 2 * R * asin(sqrt(a))

def is_within_radius(lat, lon, center_lat=CENTER_LAT, center_lon=CENTER_LON, radius_km=RADIUS_KM):
    try:
        if lat is None or lon is None:
            return False
        return haversine_km(center_lat, center_lon, float(lat), float(lon)) <= radius_km
    except Exception:
        return False

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
    t = norm_text(ev.get("title","")).lower()
    d = ""
    if ev.get("date_start"):
        try:
            d = parse_date(ev["date_start"]).strftime("%Y-%m-%d")
        except Exception:
            d = ""
    l = norm_text(ev.get("location","")).lower()
    return f"{t}::{d}::{l}"

def clamp_len(s: str, n: int) -> str:
    s = s or ""
    return (s[:n-1] + "…") if len(s) > n else s

# --- NORMALISATION GLOBALE ---
def make_event(title, date_start, url, source,
               location=None, date_end=None, price=None,
               categories=None, lat=None, lon=None, description=None):
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
        "location": norm_text(location) if location else None,
        "price": price if isinstance(price, (int, float)) else None,
        "category": sorted(list(set(categories or []))),
        "link": url or "",
        "source": source,
        "lat": lat,
        "lon": lon,
        "description": description
    }

# --- SOURCE 1 : OpenAgenda (OpenData) ---
def fetch_openagenda() -> List[Dict[str, Any]]:
    print("[OpenAgenda] récupération…")
    items = []
    rows = 200
    start = 0
    while start < 10000:
        params = {
            "dataset": OPENAGENDA_DATASET,
            "rows": rows,
            "start": start,
            "geofilter.distance": f"{CENTER_LAT},{CENTER_LON},{int(RADIUS_KM*1000)}",
            "sort": "firstdate_begin",
        }
        try:
            r = requests.get(OPENAGENDA_BASE, params=params, timeout=25)
            r.raise_for_status()
            data = r.json()
            recs = data.get("records", [])
            if not recs:
                break
            for rec in recs:
                f = rec.get("fields", {}) or {}
                title = f.get("title_fr") or f.get("title") or f.get("titre") or f.get("name") or ""
                start_dt = f.get("firstdate_begin") or f.get("lastdate_begin") or f.get("start") or f.get("date_start")
                end_dt = f.get("firstdate_end") or f.get("lastdate_end") or f.get("end") or f.get("date_end")
                if not start_dt and "timings" in f:
                    try:
                        t = json.loads(f["timings"])
                        if isinstance(t, list) and t:
                            start_dt = t[0].get("begin")
                            end_dt = t[0].get("end")
                    except Exception:
                        pass
                url = f.get("link") or f.get("url") or ""
                loc = f.get("location_name") or f.get("location_city") or f.get("location") or CITY
                lat = lon = None
                if isinstance(f.get("geo_point_2d"), dict):
                    lat = f["geo_point_2d"].get("lat")
                    lon = f["geo_point_2d"].get("lon")
                cats = []
                for key in ("tags", "keywords", "mot_cle", "themes"):
                    v = f.get(key)
                    if isinstance(v, list): cats += v
                    elif isinstance(v, str): cats.append(v)
                ev = make_event(title, start_dt, url, "openagenda", loc, end_dt, categories=cats, lat=lat, lon=lon)
                if ev:
                    items.append(ev)
            start += rows
        except Exception as e:
            print("[OpenAgenda] ERREUR:", e, file=sys.stderr)
            break
    print(f"[OpenAgenda] {len(items)} événements collectés")
    return items

# --- SOURCE 2 : Ticketmaster ---
def fetch_ticketmaster() -> List[Dict[str, Any]]:
    print("[Ticketmaster] récupération…")
    items = []
    if not TICKETMASTER_API_KEY:
        print("[Ticketmaster] Pas de clé API, source ignorée", file=sys.stderr)
        return items

    base = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        "apikey": TICKETMASTER_API_KEY,
        "latlong": f"{CENTER_LAT},{CENTER_LON}",
        "radius": str(RADIUS_KM),
        "unit": "km",
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
            venues = (ev.get("_embedded", {}) or {}).get("venues", [])
            loc_name = CITY
            lat = lon = None
            if venues:
                v = venues[0]
                loc_name = v.get("name") or (v.get("city") or {}).get("name") or CITY
                if v.get("location"):
                    lat = float(v["location"].get("latitude")) if v["location"].get("latitude") else None
                    lon = float(v["location"].get("longitude")) if v["location"].get("longitude") else None
            evn = make_event(title, start, link, "ticketmaster", loc_name, lat=lat, lon=lon)
            if evn and (evn["lat"] is None or evn["lon"] is None or is_within_radius(evn["lat"], evn["lon"])):
                items.append(evn)
    except Exception as e:
        print("[Ticketmaster] ERREUR:", e, file=sys.stderr)
    print(f"[Ticketmaster] {len(items)} événements collectés")
    return items

# --- SOURCE 3 : Meetup ICS ---
def fetch_meetup_ics() -> List[Dict[str, Any]]:
    print("[Meetup] récupération…")
    items = []
    for url in MEETUP_ICS_URLS:
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            best = from_bytes(r.content).best()
            text = best.output_text if hasattr(best, "output_text") else r.content.decode("utf-8", errors="replace")
            cal = Calendar(text)
            for ev in cal.events:
                title = ev.name or ""
                start = ev.begin.datetime if ev.begin else None
                end = ev.end.datetime if ev.end else None
                start_iso = start.astimezone(timezone.utc).isoformat() if start else None
                end_iso = end.astimezone(timezone.utc).isoformat() if end else None
                loc = ev.location or CITY
                link = ev.url or ""
                evn = make_event(title, start_iso, link, "meetup", loc, end_iso)
                if evn and CITY.lower() in norm_text(evn["location"]).lower():
                    items.append(evn)
        except Exception as e:
            print(f"[Meetup ICS] ERREUR sur {url} :", e, file=sys.stderr)
    print(f"[Meetup] {len(items)} événements collectés")
    return items

# --- SOURCE 4 : VisitPoitiers.fr (scraping complet) ---
def fetch_visitpoitiers() -> List[Dict[str, Any]]:
    print("[VisitPoitiers] Scraping complet…")
    visited = set()
    events = []

    def crawl(url, depth=0, max_depth=3):
        if url in visited or depth > max_depth or "visitpoitiers.fr" not in url:
            return
        visited.add(url)
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                return
            soup = BeautifulSoup(r.text, "html.parser")
            extract_event_from_page(url, soup)
            for link in soup.find_all("a", href=True):
                next_url = urljoin(url, link["href"])
                if VISITPOITIERS_BASE in next_url and next_url not in visited:
                    crawl(next_url, depth + 1, max_depth)
        except Exception as e:
            print(f"[VisitPoitiers] Erreur sur {url}: {e}", file=sys.stderr)
        time.sleep(0.3)

    def extract_event_from_page(url, soup):
        title_tag = soup.find("h1")
        if not title_tag:
            return
        title = title_tag.get_text(strip=True)
        # heuristique : page "activité" ou "agenda"
        if any(k in url.lower() for k in ["agenda", "activite", "evenement", "sortie"]):
            desc = soup.find("meta", {"name": "description"})
            desc = desc["content"] if desc else None
            image = soup.find("meta", {"property": "og:image"})
            image = image["content"] if image else None
            date = None
            for p in soup.find_all("p"):
                if re.search(r"\b20\d{2}\b", p.text):
                    date = p.text.strip()
                    break
            ev = make_event(title, date or START_ISO, url, "visitpoitiers",
                            location="Poitiers", description=desc)
            if ev:
                events.append(ev)

    crawl(VISITPOITIERS_BASE + "/agenda/", max_depth=3)
    crawl(VISITPOITIERS_BASE + "/activites/", max_depth=3)
    print(f"[VisitPoitiers] {len(events)} événements collectés")
    return events

# --- MAIN ---
def main():
    all_items: List[Dict[str, Any]] = []
    all_items += fetch_openagenda()
    all_items += fetch_ticketmaster()
    all_items += fetch_meetup_ics()
    all_items += fetch_visitpoitiers()

    # Déduplication
    seen = set()
    dedup = []
    for ev in all_items:
        k = dedup_key(ev)
        if k not in seen:
            seen.add(k)
            dedup.append(ev)

    # Tri
    dedup.sort(key=lambda e: parse_date(e["date_start"]) or TODAY_UTC)

    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "events": dedup}
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n✅ {len(dedup)} événements écrits dans events.json")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
