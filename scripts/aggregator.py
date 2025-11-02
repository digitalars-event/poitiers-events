#!/usr/bin/env python3
# coding: utf-8
"""
Agrégateur d'événements Poitiers (v4.0 approfondie)
- Explore VisitPoitiers
- Suit les liens externes des établissements
- Explore les sites de billetterie (CGR, Republic Corner, Weezevent, Shotgun)
- Extrait Titre + Description + Date + Image
- Supprime les doublons intelligemment
"""

import os, sys, json, re, traceback, time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import requests
from dateutil import parser as dp
from bs4 import BeautifulSoup

CITY = "Poitiers"
TODAY_UTC = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
VISITPOITIERS_BASE = "https://visitpoitiers.fr"
CACHE_FILE = "meta_cache.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PoitiersEvents/4.0; +https://visitpoitiers.fr)"}

# --- Cache ---
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        META_CACHE = json.load(f)
else:
    META_CACHE = {}

def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(META_CACHE, f, ensure_ascii=False, indent=2)

# --- Utils ---
def parse_date(text):
    """Essaye d'interpréter une date française ou internationale."""
    if not text:
        return None
    text = text.strip()
    mois = {
        "janv": "jan", "févr": "feb", "fevr": "feb", "mars": "mar", "avr": "apr",
        "mai": "may", "juin": "jun", "juil": "jul", "août": "aug",
        "sept": "sep", "oct": "oct", "nov": "nov", "déc": "dec"
    }
    for k, v in mois.items():
        text = re.sub(k, v, text, flags=re.I)
    try:
        dt = dp.parse(text, dayfirst=True, fuzzy=True)
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def norm_text(s):
    return re.sub(r"\s+", " ", (s or "").strip())

def clean_link(link):
    """Supprime les parties dynamiques (mois/année/id)."""
    return re.sub(r"/\d{4}/\d{1,2}/?", "/", link)

def dedup_key(ev):
    return f"{norm_text(ev.get('title','')).lower()}::{norm_text(ev.get('source','')).lower()}"

IGNORE_DOMAINS = [
    "facebook.com","instagram.com","linkedin.com","youtube.com","twitter.com",
    "tiktok.com","tripadvisor","google","maps","pinterest","apple.com",
    "culture.gouv.fr","booking.","pdf","applestore"
]

# --- Scrapers spécialisés ---
def scrape_cgrcinemas(base_url):
    """Scrape les séances à venir du CGR Buxerolles."""
    print("🎬 Scraping CGR Buxerolles…")
    events = []
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        films = soup.select(".movie-item, .film, .movie-card, .film-item")
        for film in films:
            title = norm_text(film.get_text())
            if not title:
                continue
            times = re.findall(r"\d{1,2}h\d{0,2}", film.get_text())
            if not times:
                continue
            events.append({
                "title": title,
                "description": "Séances à venir : " + ", ".join(times),
                "link": base_url,
                "image": "",
                "source": "cgrcinemas.fr",
                "date_start": None
            })
    except Exception as e:
        print(f"[CGR] Erreur: {e}")
    return events

def scrape_weezevent(url):
    """Scrape un lien Weezevent."""
    print(f"🎟️ Scraping Weezevent : {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if "text/html" not in r.headers.get("Content-Type", ""):
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("meta", property="og:title")
        img = soup.find("meta", property="og:image")
        desc = soup.find("meta", property="og:description")
        text = soup.get_text(" ", strip=True)
        date_match = re.search(r"\b\d{1,2}\s?(?:janv|févr|fevr|mars|avr|mai|juin|juil|août|sept|oct|nov|déc)[a-z]*\.?\s?\d{2,4}\b", text, re.I)
        date_start = parse_date(date_match.group(0)) if date_match else None
        return [{
            "title": norm_text(title["content"] if title else soup.title.string),
            "description": norm_text(desc["content"] if desc else ""),
            "link": url,
            "image": img["content"] if img else "",
            "source": "weezevent.com",
            "date_start": date_start.isoformat() if date_start else None
        }]
    except Exception as e:
        print(f"[Weezevent] Erreur: {e}")
        return None

def scrape_shotgun(url):
    """Scrape un lien Shotgun."""
    print(f"💥 Scraping Shotgun : {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("meta", property="og:title")
        img = soup.find("meta", property="og:image")
        desc = soup.find("meta", property="og:description")
        text = soup.get_text(" ", strip=True)
        date_match = re.search(r"\b\d{1,2}\s?(?:janv|févr|mars|avr|mai|juin|juil|août|sept|oct|nov|déc)\b", text, re.I)
        date_start = parse_date(date_match.group(0)) if date_match else None
        return [{
            "title": norm_text(title["content"] if title else soup.title.string),
            "description": norm_text(desc["content"] if desc else ""),
            "link": url,
            "image": img["content"] if img else "",
            "source": "shotgun.live",
            "date_start": date_start.isoformat() if date_start else None
        }]
    except Exception as e:
        print(f"[Shotgun] Erreur: {e}")
        return None

def scrape_republic_corner(base_url):
    """Scrape les affiches d’événements du Republic Corner."""
    print(f"🎶 Scraping Republic Corner : {base_url}")
    events = []
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.select("img[src*='uploads'], img[src*='event'], img[src*='affiche']")
        for b in blocks:
            img = urljoin(base_url, b["src"])
            alt = b.get("alt") or ""
            parent = b.find_parent("a")
            link = urljoin(base_url, parent["href"]) if parent and parent.get("href") else base_url
            title = norm_text(alt or os.path.basename(img).split(".")[0])
            events.append({
                "title": title,
                "description": "Événement au Republic Corner",
                "link": link,
                "image": img,
                "source": "republic-corner.fr",
                "date_start": None
            })
    except Exception as e:
        print(f"[Republic Corner] Erreur: {e}")
    return events

# --- Exploration d’un site générique ---
def explore_external_site(base_url):
    """Explore un site externe à la recherche d'événements."""
    print(f"🔎 Exploration du site externe : {base_url}")
    domain = urlparse(base_url).netloc.replace("www.", "")
    if domain in META_CACHE:
        print(f"🧠 Cache utilisé pour {domain}")
        return META_CACHE[domain]

    # Scrapers spécialisés
    if "cgrcinemas.fr" in domain:
        events = scrape_cgrcinemas(base_url)
    elif "republic-corner.fr" in domain:
        events = scrape_republic_corner(base_url)
    elif "weezevent.com" in domain:
        events = scrape_weezevent(base_url) or []
    elif "shotgun.live" in domain:
        events = scrape_shotgun(base_url) or []
    else:
        events = []

    META_CACHE[domain] = events
    save_cache()
    print(f"✅ {len(events)} événements trouvés sur {domain}")
    return events

# --- Scraper principal VisitPoitiers ---
def fetch_visitpoitiers_events():
    sitemap_url = f"{VISITPOITIERS_BASE}/plan-du-site/"
    visited, all_events = set(), []

    try:
        r = requests.get(sitemap_url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        activity_links = [a["href"] for a in soup.select(".elementor-sitemap-activite-list a[href]")]
        print(f"[VisitPoitiers] {len(activity_links)} établissements détectés")

        for link in activity_links:
            if link in visited:
                continue
            visited.add(link)
            time.sleep(0.3)
            try:
                r2 = requests.get(link, headers=HEADERS, timeout=10)
                soup2 = BeautifulSoup(r2.text, "html.parser")

                external_links = [
                    a["href"] for a in soup2.select("a[href]")
                    if a["href"].startswith("http") and "visitpoitiers.fr" not in a["href"]
                ]

                for href in external_links:
                    if any(bad in href for bad in IGNORE_DOMAINS):
                        continue
                    print(f"🌐 Exploration de {href}")
                    sub_events = explore_external_site(href)
                    all_events.extend(sub_events)

            except Exception as e:
                print(f"[VisitPoitiers] Erreur sur {link}: {e}")

    except Exception as e:
        print(f"[VisitPoitiers] ERREUR principale: {e}")

    print(f"🎯 Total : {len(all_events)} événements collectés")
    return all_events

# --- Main ---
def main():
    all_items = fetch_visitpoitiers_events()
    dedup, seen = [], set()
    for e in all_items:
        k = dedup_key(e)
        if k not in seen and e.get("title") and (e.get("date_start") or e.get("description")):
            seen.add(k)
            dedup.append(e)
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "events": dedup},
                  f, ensure_ascii=False, indent=2)
    print(f"💾 {len(dedup)} événements sauvegardés dans events.json")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
