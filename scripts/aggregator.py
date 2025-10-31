#!/usr/bin/env python3
# coding: utf-8
"""
Aggregateur d'événements Poitiers (MVP)
Sources:
- OpenAgenda via OpenData (dataset 'evenements-publics-openagenda' sur public.opendatasoft.com)
- Eventbrite (API v3 /events/search) -> nécessite EVENTBRITE_TOKEN
- Ticketmaster Discovery API -> nécessite TICKETMASTER_API_KEY
- Meetup (flux ICS publics de groupes listés)
Sortie: events.json normalisé, trié par date croissante
"""

import os, sys, json, math, time, re, traceback
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

import requests

# Dépendances tierces installées via requirements.txt
from dateutil import parser as dp
import feedparser  # Pour RSS si besoin futur / Google Alerts
from ics import Calendar  # pour parser les ICS Meetup (simple)

# --- Paramètres généraux ---
CITY = "Poitiers"
CENTER_LAT = 46.5802
CENTER_LON = 0.3404
RADIUS_KM = 30  # rayon autour de Poitiers

TODAY_UTC = datetime.now(timezone.utc)

# Meetup: liste de flux ICS (ajoute/retire ce que tu veux)
MEETUP_ICS_URLS = [
    # Exemple: "https://www.meetup.com/<groupe>/events/ical"
]

# Secrets (via GitHub Actions > Settings > Secrets & variables > Actions)
EVENTBRITE_TOKEN = os.getenv("EVENTBRITE_TOKEN", "").strip()
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY", "").strip()

# Opendatasoft dataset OpenAgenda public
OPENAGENDA_DATASET = "evenements-publics-openagenda"
OPENAGENDA_BASE = "https://public.opendatasoft.com/api/records/1.0/search/"

# --- Utils géo ---
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def is_within_radius(lat, lon, center_lat=CENTER_LAT, center_lon=CENTER_LON, radius_km=RADIUS_KM):
    try:
        if lat is None or lon is None:
            return False
        return haversine_km(center_lat, center_lon, float(lat), float(lon)) <= radius_km
    except:
        return False

def parse_date(iso_or_text) -> Optional[datetime]:
    if not iso_or_text:
        return None
    try:
        dt = dp.parse(iso_or_text)
        if not dt.tzinfo:
            # Assume local/naive -> mettre en UTC pour comparaison fiable
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except:
        return None

def is_future(dt: Optional[datetime]) -> bool:
    if not dt:
        return False
    return dt >= TODAY_UTC

def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def dedup_key(ev: Dict[str, Any]) -> str:
    # clé de déduplication simple: titre normalisé + date_debut au jour près + lieu
    t = norm_text(ev.get("title","")).lower()
    d = ""
    if ev.get("date_start"):
        d = parse_date(ev["date_start"]).strftime("%Y-%m-%d")
    l = norm_text(ev.get("location","")).lower()
    return f"{t}::{d}::{l}"

def clamp_len(s: str, n: int) -> str:
    s = s or ""
    return (s[:n-1] + "…") if len(s) > n else s

# --- Normalisation des événements ---
def make_event(
    title: str,
    date_start: Optional[str],
    url: str,
    source: str,
    location: Optional[str] = None,
    date_end: Optional[str] = None,
    price: Optional[float] = None,
    categories: Optional[List[str]] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    description: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    title = clamp_len(norm_text(title), 220)
    if not title:
        return None
    ds = parse_date(date_start) if date_start else None
    if not ds or not is_future(ds):
        return None  # on ne garde que les événements à venir
    ev = {
        "title": title,
        "date_start": ds.isoformat(),
        "date_end": parse_date(date_end).isoformat() if date_end else None,
        "location": norm_text(location) if location else None,
        "price": price if isinstance(price, (int,float)) else None,
        "category": sorted(list(set(categories or []))),
        "link": url or "",
        "source": source,
        "lat": lat,
        "lon": lon
    }
    return ev

# --- Source 1: OpenAgenda via OpenData (Opendatasoft) ---
def fetch_openagenda() -> List[Dict[str,Any]]:
    items = []
    # Filtrage par rayon: l'API ODS ne fait pas un vrai filtre géo par rayon facilement.
    # On récupère par mot-clé Poitiers + une fenêtre de dates futures,
    # puis on filtre côté code par distance si on a des coords.
    params = {
        "dataset": OPENAGENDA_DATASET,
        "q": CITY,
        "rows": 200,          # augmenter si besoin
        "sort": "start",      # croissant
    }
    try:
        r = requests.get(OPENAGENDA_BASE, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        for rec in data.get("records", []):
            f = rec.get("fields", {})
            title = f.get("title") or f.get("name") or f.get("titre") or ""
            start = f.get("start") or f.get("date_start") or f.get("date_debut")
            end = f.get("end") or f.get("date_end") or f.get("date_fin")
            url = f.get("link") or f.get("url") or ""
            loc = f.get("location_name") or f.get("location") or f.get("lieu") or f.get("city") or "Poitiers"
            lat = None
            lon = None
            # Plusieurs formats possibles pour coords selon agendas:
            if "latlon" in f and isinstance(f["latlon"], list) and len(f["latlon"])==2:
                lat, lon = f["latlon"][0], f["latlon"][1]
            elif "geo_point_2d" in f and isinstance(f["geo_point_2d"], dict):
                lat, lon = f["geo_point_2d"].get("lat"), f["geo_point_2d"].get("lon")

            cats = []
            for key in ("tags","keywords","mot_cle"):
                v = f.get(key)
                if isinstance(v, list): cats.extend(v)
                elif isinstance(v, str): cats.extend([v])

            ev = make_event(
                title=title,
                date_start=start,
                date_end=end,
                url=url,
                source="openagenda",
                location=loc,
                categories=cats,
                lat=lat, lon=lon
            )
            if not ev:
                continue
            # filtre rayon si on a coords; sinon garder si location contient Poitiers / Grand Poitiers
            if ev["lat"] is not None and ev["lon"] is not None:
                if not is_within_radius(ev["lat"], ev["lon"]):
                    continue
            else:
                if CITY.lower() not in norm_text(ev["location"]).lower():
                    # essaie mot-clef "Poitiers" pour limiter
                    continue
            items.append(ev)
    except Exception as e:
        print("[OpenAgenda] ERREUR:", e, file=sys.stderr)
    return items

# --- Source 2: Eventbrite ---
def fetch_eventbrite() -> List[Dict[str,Any]]:
    items = []
    if not EVENTBRITE_TOKEN:
        print("[Eventbrite] Pas de token, source ignorée", file=sys.stderr)
        return items
    url = "https://www.eventbriteapi.com/v3/events/search/"
    # Stratégie : centre sur Poitiers (lat/lon) + rayon 50km ; date >= now ; seulement événements publics
    params = {
        "location.latitude": CENTER_LAT,
        "location.longitude": CENTER_LON,
        "location.within": "50km",
        "expand": "venue",
        "start_date.range_start": TODAY_UTC.isoformat(),
        "sort_by": "date",
    }
    headers = {"Authorization": f"Bearer {EVENTBRITE_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        for ev in data.get("events", []):
            title = (ev.get("name") or {}).get("text") or ev.get("name","")
            start = (ev.get("start") or {}).get("utc")
            end = (ev.get("end") or {}).get("utc")
            link = ev.get("url") or ""
            venue = ev.get("venue") or {}
            loc_name = venue.get("name") or venue.get("address",{}).get("city") or "Poitiers"
            lat = None; lon = None
            if venue.get("address"):
                try:
                    lat = float(venue["address"].get("latitude")) if venue["address"].get("latitude") else None
                    lon = float(venue["address"].get("longitude")) if venue["address"].get("longitude") else None
                except:
                    pass

            evn = make_event(
                title=title,
                date_start=start,
                date_end=end,
                url=link,
                source="eventbrite",
                location=loc_name,
                lat=lat, lon=lon
            )
            if not evn: 
                continue
            # rayon
            if evn["lat"] is not None and evn["lon"] is not None:
                if not is_within_radius(evn["lat"], evn["lon"]):
                    continue
            items.append(evn)
    except Exception as e:
        print("[Eventbrite] ERREUR:", e, file=sys.stderr)
    return items

# --- Source 3: Ticketmaster ---
def fetch_ticketmaster() -> List[Dict[str,Any]]:
    items = []
    if not TICKETMASTER_API_KEY:
        print("[Ticketmaster] Pas de clé API, source ignorée", file=sys.stderr)
        return items
    base = "https://app.ticketmaster.com/discovery/v2/events.json"
    # Stratégie: France + rayon autour de Poitiers (via latlong) + date >= now
    params = {
        "apikey": TICKETMASTER_API_KEY,
        "countryCode": "FR",
        "latlong": f"{CENTER_LAT},{CENTER_LON}",
        "radius": str(RADIUS_KM),
        "unit": "km",
        "startDateTime": TODAY_UTC.isoformat().replace("+00:00","Z"),
        "size": "100"
    }
    try:
        r = requests.get(base, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        events = data.get("_embedded", {}).get("events", [])
        for ev in events:
            title = ev.get("name","")
            dates = ev.get("dates",{})
            start = (dates.get("start") or {}).get("dateTime")
            end = None
            link = ev.get("url","")
            venues = (ev.get("_embedded",{}) or {}).get("venues",[])
            loc_name = "Poitiers"
            lat=lon=None
            if venues:
                v = venues[0]
                loc_name = v.get("name") or v.get("city",{}).get("name") or "Poitiers"
                try:
                    lat = float(v.get("location",{}).get("latitude")) if v.get("location",{}).get("latitude") else None
                    lon = float(v.get("location",{}).get("longitude")) if v.get("location",{}).get("longitude") else None
                except:
                    pass

            evn = make_event(
                title=title,
                date_start=start,
                date_end=end,
                url=link,
                source="ticketmaster",
                location=loc_name,
                lat=lat, lon=lon
            )
            if not evn:
                continue
            # rayon
            if evn["lat"] is not None and evn["lon"] is not None:
                if not is_within_radius(evn["lat"], evn["lon"]):
                    continue
            items.append(evn)
    except Exception as e:
        print("[Ticketmaster] ERREUR:", e, file=sys.stderr)
    return items

# --- Source 4: Meetup ICS ---
def fetch_meetup_ics() -> List[Dict[str,Any]]:
    items = []
    for url in MEETUP_ICS_URLS:
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            cal = Calendar(r.text)
            for ev in cal.events:
                title = ev.name or ""
                start = ev.begin.datetime if ev.begin else None
                end = ev.end.datetime if ev.end else None
                # normaliser en ISO
                start_iso = start.astimezone(timezone.utc).isoformat() if start else None
                end_iso = end.astimezone(timezone.utc).isoformat() if end else None

                # Meetup ICS n'a pas toujours les coords; on filtre par ville/lieu
                loc = ev.location or "Poitiers"
                link = ev.url or ""

                evn = make_event(
                    title=title,
                    date_start=start_iso,
                    date_end=end_iso,
                    url=link,
                    source="meetup",
                    location=loc
                )
                if not evn:
                    continue
                # Filtrage grossier: garder si la mention Poitiers apparait ou laisser passer (rayon indispo)
                if CITY.lower() not in norm_text(evn["location"]).lower():
                    continue
                items.append(evn)
        except Exception as e:
            print(f"[Meetup ICS] ERREUR sur {url} :", e, file=sys.stderr)
    return items

def main():
    all_items: List[Dict[str,Any]] = []
    print("==> Récupération OpenAgenda (OpenData)")
    all_items += fetch_openagenda()

    print("==> Récupération Eventbrite")
    all_items += fetch_eventbrite()

    print("==> Récupération Ticketmaster")
    all_items += fetch_ticketmaster()

    print("==> Récupération Meetup ICS")
    all_items += fetch_meetup_ics()

    # Déduplication
    seen = set()
    dedup = []
    for ev in all_items:
        k = dedup_key(ev)
        if k not in seen:
            seen.add(k)
            dedup.append(ev)

    # Tri par date
    dedup.sort(key=lambda e: parse_date(e["date_start"]))

    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "events": dedup}
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"OK - {len(dedup)} événements écrits dans events.json")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
