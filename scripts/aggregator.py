#!/usr/bin/env python3
# coding: utf-8
"""
Agrégateur d'événements Poitiers (MVP sans Eventbrite)
Sources actives :
- OpenAgenda via OpenData (Opendatasoft, dataset 'evenements-publics-openagenda')
- Ticketmaster Discovery API (clé: TICKETMASTER_API_KEY)
- Meetup (flux ICS publics listés)
Sortie: events.json normalisé, trié par date croissante
"""

import os, sys, json, math, re, traceback
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import requests
from dateutil import parser as dp
from ics import Calendar
from charset_normalizer import from_bytes  # pour décoder proprement les ICS

# --- Paramètres généraux ---
CITY = "Poitiers"
CENTER_LAT = 46.5802
CENTER_LON = 0.3404
RADIUS_KM = 30  # rayon autour de Poitiers

TODAY_UTC = datetime.now(timezone.utc)
START_ISO = TODAY_UTC.strftime("%Y-%m-%dT%H:%M:%SZ")  # format sans millisecondes

# Meetup: liste de flux ICS (ajoute/retire librement)
MEETUP_ICS_URLS = [
    "https://www.meetup.com/human-talks-poitiers/events/ical",
    "https://www.meetup.com/fr-FR/afup-poitiers-php/events/ical",
    "https://www.meetup.com/poitiers-aws-user-group/events/ical"
]

# Secrets (GitHub Actions -> Settings -> Secrets and variables -> Actions)
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY", "").strip()

# Opendatasoft / OpenAgenda
OPENAGENDA_DATASET = "evenements-publics-openagenda"
OPENAGENDA_BASE = "https://public.opendatasoft.com/api/records/1.0/search/"

# --- Utils géo ---
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
        dt = dp.parse(iso_or_text)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def is_future(dt: Optional[datetime]) -> bool:
    return bool(dt and dt >= TODAY_UTC)

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

# --- Normalisation ---
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
    if not ds or (ds < TODAY_UTC - timedelta(days=1)):
        return None
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

# --- Source 1: OpenAgenda via Opendatasoft (pagination) ---
def fetch_openagenda() -> List[Dict[str,Any]]:
    items: List[Dict[str,Any]] = []
    rows = 200
    start = 0
    # On boucle jusqu'à ce que la page soit vide ou qu'on atteigne ~2000 éléments
    while start < 2000:
        params = {
            "dataset": OPENAGENDA_DATASET,
            "rows": rows,
            "start": start,
            "q": CITY,  # filtrage textuel plus large
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
                title = (
                    f.get("title_fr")
                    or f.get("title")
                    or f.get("titre")
                    or f.get("name")
                    or ""
                )
                start_dt = (
                    f.get("firstdate_begin")
                    or f.get("lastdate_begin")
                    or f.get("start")
                    or f.get("date_start")
                )
                end_dt = (
                    f.get("firstdate_end")
                    or f.get("lastdate_end")
                    or f.get("end")
                    or f.get("date_end")
                )
                
                # Si toujours vide, on essaie de parser timings
                if not start_dt and "timings" in f:
                    import json
                    try:
                        t = json.loads(f["timings"])
                        if isinstance(t, list) and t:
                            start_dt = t[0].get("begin")
                            end_dt = t[0].get("end")
                    except Exception:
                        pass
                url = f.get("link") or f.get("url") or ""
                loc = (
                    f.get("location_name")
                    or f.get("location_city")
                    or f.get("location")
                    or f.get("lieu")
                    or f.get("city")
                    or CITY
                )
                lat = lon = None
                if isinstance(f.get("geo_point_2d"), dict):
                    lat = f["geo_point_2d"].get("lat")
                    lon = f["geo_point_2d"].get("lon")
                elif isinstance(f.get("latlon"), list) and len(f["latlon"]) == 2:
                    lat, lon = f["latlon"]
                if not lat or not lon:
                    lat, lon = CENTER_LAT, CENTER_LON  # fallbac

                cats = []
                for key in ("tags","keywords","mot_cle","themes"):
                    v = f.get(key)
                    if isinstance(v, list): cats += v
                    elif isinstance(v, str): cats.append(v)

                ev = make_event(
                    title=title, date_start=start_dt, date_end=end_dt, url=url,
                    source="openagenda", location=loc, categories=cats, lat=lat, lon=lon
                )
                if ev:
                    items.append(ev)
            start += rows
        except Exception as e:
            print("[OpenAgenda] ERREUR:", e, file=sys.stderr)
            break
    return items

# --- Source 2: Ticketmaster ---
def fetch_ticketmaster() -> List[Dict[str,Any]]:
    items: List[Dict[str,Any]] = []
    if not TICKETMASTER_API_KEY:
        print("[Ticketmaster] Pas de clé API, source ignorée", file=sys.stderr)
        return items

    base = "https://app.ticketmaster.com/discovery/v2/events.json"

    # Essai 1: ville = Poitiers (souvent suffisant)
    params_city = {
        "apikey": TICKETMASTER_API_KEY,
        "countryCode": "FR",
        "city": CITY,
        "startDateTime": START_ISO,
        "size": "100"
    }
    
    params_geo = {
        "apikey": TICKETMASTER_API_KEY,
        "latlong": f"{CENTER_LAT},{CENTER_LON}",
        "radius": str(RADIUS_KM),
        "unit": "km",
        "startDateTime": START_ISO,
        "size": "100"
    }
    def harvest(params):
        try:
            r = requests.get(base, params=params, timeout=25)
            r.raise_for_status()
            data = r.json()
            for ev in data.get("_embedded", {}).get("events", []):
                title = ev.get("name","")
                start = (ev.get("dates",{}).get("start") or {}).get("dateTime")
                link = ev.get("url","")
                venues = (ev.get("_embedded",{}) or {}).get("venues",[])
                loc_name = CITY; lat = lon = None
                if venues:
                    v = venues[0]
                    loc_name = v.get("name") or (v.get("city") or {}).get("name") or CITY
                    if v.get("location"):
                        try:
                            lat = float(v["location"].get("latitude")) if v["location"].get("latitude") else None
                            lon = float(v["location"].get("longitude")) if v["location"].get("longitude") else None
                        except Exception:
                            pass
                evn = make_event(title, start, link, "ticketmaster", loc_name, lat=lat, lon=lon)
                if evn and (evn["lat"] is None or evn["lon"] is None or is_within_radius(evn["lat"], evn["lon"])):
                    items.append(evn)
        except Exception as e:
            print("[Ticketmaster] ERREUR:", e, file=sys.stderr)

    harvest(params_city)
    if not items:
        harvest(params_geo)

    return items

# --- Source 3: Meetup ICS (avec décodage robuste) ---
def fetch_meetup_ics() -> List[Dict[str,Any]]:
    items: List[Dict[str,Any]] = []
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
                if not evn:
                    continue
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
    dedup.sort(key=lambda e: parse_date(e["date_start"]) or TODAY_UTC)

    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "events": dedup}
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"OK - {len(dedup)} événements écrits dans events.json")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
