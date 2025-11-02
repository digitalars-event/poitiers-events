#!/usr/bin/env python3
# coding: utf-8
"""
Agrégateur d'événements Poitiers (version améliorée)
- Explore les établissements listés sur VisitPoitiers
- Suit les liens externes officiels
- Extrait titres, dates, descriptions, images
- Nettoie les doublons (même titre / même source)
- Gère les encodages et descriptions longues
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
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PoitiersEvents/3.1; +https://visitpoitiers.fr)"}

# --- Cache ---
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        META_CACHE = json.load(f)
else:
    META_CACHE = {}

def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(META_CACHE, f, ensure_ascii=False, indent=2)

def parse_date(text):
    """Tente d'extraire une date (formats FR)"""
    if not text:
        return None
    try:
        # Ajout support mois FR
        mois = {
            "janv": "jan", "févr": "feb", "fevr": "feb", "mars": "mar",
            "avr": "apr", "mai": "may", "juin": "jun", "juil": "jul",
            "août": "aug", "sept": "sep", "oct": "oct", "nov": "nov", "déc": "dec"
        }
        for k, v in mois.items():
            text = re.sub(k, v, text, flags=re.I)
        dt = dp.parse(text, dayfirst=True, fuzzy=True)
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def norm_text(s):
    return re.sub(r"\s+", " ", (s or "").strip())

def clean_link(link):
    """Supprime les parties dynamiques des URLs (mois/année)"""
    return re.sub(r"/\d{4}/\d{1,2}/?", "/", link)

def dedup_key(ev):
    return f"{norm_text(ev.get('title','')).lower()}::{norm_text(ev.get('source','')).lower()}"

IGNORE_DOMAINS = [
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "tiktok.com", "tripadvisor", "google", "maps",
    "pinterest", "apple.com", "culture.gouv.fr", "booking.", ".pdf"
]

# --- Analyse d’un site externe ---
def explore_external_site(base_url):
    """Explore un site externe à la recherche d'événements"""
    print(f"🔎 Exploration du site externe : {base_url}")
    domain = urlparse(base_url).netloc.replace("www.", "")
    if domain in META_CACHE:
        print(f"🧠 Cache utilisé pour {domain}")
        return META_CACHE[domain]

    events, visited = [], set()
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=12)
        r.encoding = r.apparent_encoding or "utf-8"
        if "text/html" not in r.headers.get("Content-Type", ""):
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        links = [urljoin(base_url, a["href"]) for a in soup.select("a[href]")]
        links = [l for l in links if l.startswith(base_url)]

        keywords = ["evenement", "agenda", "soiree", "concert", "spectacle", "festival", "sortie", "programmation"]
        target_links = [l for l in links if any(k in l.lower() for k in keywords)]
        if not target_links:
            target_links = links[:5]

        for link in target_links[:10]:
            if link in visited:
                continue
            visited.add(link)
            time.sleep(0.3)
            try:
                r2 = requests.get(link, headers=HEADERS, timeout=10)
                r2.encoding = r2.apparent_encoding or "utf-8"
                if "text/html" not in r2.headers.get("Content-Type", ""):
                    continue
                soup2 = BeautifulSoup(r2.text, "html.parser")

                blocks = soup2.find_all(["article", "div"], class_=re.compile("event|agenda|show|spectacle|card", re.I))
                for b in blocks:
                    title_tag = b.find(["h1", "h2", "h3"])
                    title = norm_text(title_tag.get_text()) if title_tag else None
                    if not title:
                        continue

                    desc_tags = b.find_all(["p", "div"], class_=re.compile("desc|text|content|body|resume", re.I))
                    desc = " ".join(norm_text(t.get_text()) for t in desc_tags) or ""

                    img_tag = b.find("img")
                    img = urljoin(link, img_tag["src"]) if img_tag and img_tag.get("src") else ""

                    text = b.get_text(" ", strip=True)
                    date_match = re.search(
                        r"\b(\d{1,2}\s?(?:janv|févr|fevr|mars|avr|mai|juin|juil|août|sept|oct|nov|déc)[a-z]*\.?\s?\d{2,4})\b",
                        text, re.I)
                    if not date_match:
                        date_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", text)
                    date_start = parse_date(date_match.group(1)) if date_match else None
                    if date_start and date_start < TODAY_UTC:
                        continue

                    events.append({
                        "title": title,
                        "description": desc,
                        "link": clean_link(link),
                        "image": img,
                        "source": domain,
                        "date_start": date_start.isoformat() if date_start else None
                    })
            except Exception as e:
                print(f"[EXTERNAL] Erreur sur {link}: {e}")

    except Exception as e:
        print(f"[EXTERNAL] Erreur principale sur {base_url}: {e}")

    META_CACHE[domain] = events
    save_cache()
    print(f"✅ {len(events)} événements trouvés sur {domain}")
    return events

# --- Scraper VisitPoitiers ---
def fetch_visitpoitiers_events():
    sitemap_url = f"{VISITPOITIERS_BASE}/plan-du-site/"
    visited, all_events = set(), []

    try:
        r = requests.get(sitemap_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        activity_links = [a["href"] for a in soup.select(".elementor-sitemap-activite-list a[href]")]
        print(f"[VisitPoitiers] {len(activity_links)} établissements détectés")

        for link in activity_links:
            if link in visited:
                continue
            visited.add(link)
            time.sleep(0.4)

            try:
                r2 = requests.get(link, headers=HEADERS, timeout=10)
                if "text/html" not in r2.headers.get("Content-Type", ""):
                    continue
                soup2 = BeautifulSoup(r2.text, "html.parser")

                external_link = None
                for a in soup2.select("a[href]"):
                    href = a["href"]
                    if href.startswith("http") and "visitpoitiers.fr" not in href:
                        if not any(bad in href for bad in IGNORE_DOMAINS):
                            external_link = href
                            break

                if not external_link:
                    continue

                print(f"🌐 Exploration de {external_link}")
                site_events = explore_external_site(external_link)
                all_events.extend(site_events)

            except Exception as e:
                print(f"[VisitPoitiers] Erreur sur {link}: {e}")

    except Exception as e:
        print(f"[VisitPoitiers] ERREUR principale: {e}")

    print(f"🎯 Total : {len(all_events)} événements collectés")
    return all_events

def main():
    all_items = fetch_visitpoitiers_events()
    dedup, seen = [], set()
    for e in all_items:
        k = dedup_key(e)
        if k not in seen:
            seen.add(k)
            dedup.append(e)
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "events": dedup}, f, ensure_ascii=False, indent=2)
    print(f"💾 {len(dedup)} événements sauvegardés dans events.json")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
