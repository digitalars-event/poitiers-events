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


def parse_date(text) -> Optional[datetime]:
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


def make_event(title, date_start, url, source, location=None, date_end=None, description=None, image=None):
    title = clamp_len(norm_text(title), 220)
    if not title:
        return None

    ds = parse_date(date_start)
    if ds and ds < TODAY_UTC:
        return None

    ev = {
        "title": title,
        "location": norm_text(location or CITY),
        "link": url or "",
        "source": source,
        "description": norm_text(description or ""),
        "image": image or ""
    }

    # Ajout des dates uniquement pour les vrais événements
    if ds:
        ev["date_start"] = ds.isoformat()
        if date_end:
            ev["date_end"] = parse_date(date_end).isoformat()

    return ev


def fetch_visitpoitiers():
    print("[VisitPoitiers] Scraping depuis le plan du site (avec images)…")
    base = VISITPOITIERS_BASE
    sitemap_url = f"{base}/plan-du-site/"
    visited, events = set(), []

    try:
        r = requests.get(sitemap_url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        activity_links = [a["href"] for a in soup.select(".elementor-sitemap-activite-list a[href]")]
        event_links = [a["href"] for a in soup.select(".elementor-sitemap-evenement-list a[href]")]
        all_links = list(set(activity_links + event_links))

        print(f" - {len(activity_links)} activités et {len(event_links)} événements détectés.")

        for link in all_links:
            if link in visited:
                continue
            visited.add(link)
            time.sleep(0.3)

            try:
                r2 = requests.get(link, timeout=15)
                if "text/html" not in r2.headers.get("Content-Type", ""):
                    continue
                soup2 = BeautifulSoup(r2.text, "html.parser")

                title_tag = soup2.find("h1")
                title = title_tag.get_text(strip=True) if title_tag else link.split("/")[-2].replace("-", " ").title()
                desc_tag = soup2.find("p")
                desc = desc_tag.get_text(strip=True) if desc_tag else ""

                address = ""
                for p in soup2.find_all("p"):
                    if any(v in p.text for v in ["Poitiers", "Saint-Benoît", "Chauvigny", "Ligugé", "Chasseneuil"]):
                        address = norm_text(p.text)
                        break

                image_url = None
                img_tag = soup2.find("img")
                if img_tag and img_tag.get("src"):
                    image_url = urljoin(link, img_tag["src"])
                else:
                    bg_div = soup2.find("div", style=re.compile("background-image", re.I))
                    if bg_div:
                        match = re.search(r'url\(["\']?(.*?)["\']?\)', bg_div["style"])
                        if match:
                            image_url = urljoin(link, match.group(1))

                source_type = "visitpoitiers-activite" if "/activite/" in link else "visitpoitiers-evenement"

                ev = make_event(
                    title=title,
                    date_start=None if "activite" in link else START_ISO,
                    url=link,
                    source=source_type,
                    location=address or "Grand Poitiers",
                    description=desc,
                    image=image_url
                )
                if ev:
                    events.append(ev)

            except Exception as e:
                print(f"[VisitPoitiers] Erreur sur {link}: {e}")

    except Exception as e:
        print("[VisitPoitiers] ERREUR sur le plan du site:", e)

    print(f"[VisitPoitiers] {len(events)} pages collectées (activités + événements)")
    return events


def main():
    all_items = fetch_visitpoitiers()

    dedup, seen = [], set()
    for e in all_items:
        k = dedup_key(e)
        if k not in seen:
            seen.add(k)
            dedup.append(e)

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "events": dedup},
                  f, ensure_ascii=False, indent=2)
    print(f"\n✅ {len(dedup)} éléments écrits dans events.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
