#!/usr/bin/env python3
# coding: utf-8
"""
Agrégateur d'établissements et événements VisitPoitiers
- Récupère adresses + horaires d'ouverture + images + liens externes
- Stocke les métadonnées externes en cache
- Détecte les séances de cinéma CGR
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
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PoitiersScraper/2.0; +https://visitpoitiers.fr)"}

# Charger le cache existant
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        META_CACHE = json.load(f)
else:
    META_CACHE = {}

def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(META_CACHE, f, ensure_ascii=False, indent=2)

def parse_date(text):
    try:
        dt = dp.parse(str(text), dayfirst=True, fuzzy=True)
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def norm_text(s):
    return re.sub(r"\s+", " ", (s or "").strip())

def dedup_key(ev):
    return f"{norm_text(ev.get('title','')).lower()}::{norm_text(ev.get('link','')).lower()}"

IGNORE_DOMAINS = [
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "tiktok.com", "tripadvisor", "google", "maps", "pinterest"
]

EVENT_DOMAINS = [
    "billetweb.fr", "eventbrite.fr", "helloasso.com", "weezevent.com", "yurplan.com", "cgrcinemas.fr"
]

# --- Extraction de métadonnées externes ---
def extract_external_metadata(url):
    """Récupère les métadonnées d'un lien externe avec cache"""
    if url in META_CACHE:
        return META_CACHE[url]

    meta = {"title": None, "description": None, "image": None, "date_start": None, "events": []}
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if "text/html" not in r.headers.get("Content-Type", ""):
            return meta
        soup = BeautifulSoup(r.text, "html.parser")

        og_title = soup.find("meta", property="og:title")
        og_desc = soup.find("meta", property="og:description")
        og_image = soup.find("meta", property="og:image")

        meta["title"] = norm_text(og_title["content"]) if og_title else (soup.title.string if soup.title else None)
        meta["description"] = norm_text(og_desc["content"]) if og_desc else ""
        meta["image"] = og_image["content"] if og_image else ""

        # Détection spéciale pour CGR
        if "cgrcinemas.fr" in url:
            meta["events"] = extract_cgr_showtimes(url, soup)

    except Exception as e:
        print(f"[META] Erreur sur {url}: {e}")

    META_CACHE[url] = meta
    save_cache()
    return meta

# --- Extraction des horaires CGR ---
def extract_cgr_showtimes(url, soup):
    """Détecte et extrait les séances de films sur le site CGR."""
    showtimes = []
    try:
        blocks = soup.find_all("div", class_=re.compile("showtimes|movie|film", re.I))
        for b in blocks[:10]:
            title = b.find("h3") or b.find("h2")
            movie_title = title.get_text(strip=True) if title else "Séance"
            times = re.findall(r"\b\d{1,2}h\d{0,2}\b", b.get_text(" ", strip=True))
            if times:
                showtimes.append({"film": movie_title, "horaires": times})
    except Exception as e:
        print(f"[CGR] Erreur extraction séances: {e}")
    return showtimes


# --- Extraction principale VisitPoitiers ---
def fetch_visitpoitiers():
    sitemap_url = f"{VISITPOITIERS_BASE}/plan-du-site/"
    visited, results = set(), []

    try:
        r = requests.get(sitemap_url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        all_links = [a["href"] for a in soup.select(".elementor-sitemap-activite-list a[href], .elementor-sitemap-evenement-list a[href]")]
        print(f"[VisitPoitiers] {len(all_links)} liens détectés")

        for link in all_links[:150]:
            if link in visited:
                continue
            visited.add(link)
            time.sleep(0.3)

            try:
                r2 = requests.get(link, headers=HEADERS, timeout=10)
                soup2 = BeautifulSoup(r2.text, "html.parser")

                # --- TITRE & DESCRIPTION ---
                title = (soup2.find("h1") or {}).get_text(strip=True)
                desc = (soup2.find("p") or {}).get_text(strip=True)
                og_img = soup2.find("meta", property="og:image")
                image = og_img["content"] if og_img else ""

                # --- ADRESSE ---
                address = ""
                for p in soup2.find_all("p"):
                    if any(v in p.text for v in ["Poitiers", "Saint-Benoît", "Chauvigny", "Ligugé", "Chasseneuil"]):
                        address = norm_text(p.text)
                        break

                # --- HORAIRES D’OUVERTURE ---
                opening_hours = []
                for ul in soup2.find_all("ul"):
                    text = norm_text(ul.get_text(" ", strip=True))
                    if any(word in text.lower() for word in ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]):
                        opening_hours.append(text)
                if not opening_hours:
                    for p in soup2.find_all("p"):
                        text = p.get_text(" ", strip=True)
                        if re.search(r"\d{1,2}h", text):
                            opening_hours.append(norm_text(text))

                ev = {
                    "title": norm_text(title),
                    "description": norm_text(desc),
                    "link": link,
                    "image": image,
                    "source": "visitpoitiers",
                    "address": address or "",
                    "opening_hours": opening_hours or []
                }
                results.append(ev)

                # --- LIENS EXTERNES UTILES ---
                for a in soup2.select("a[href]"):
                    href = a["href"]
                    if not href.startswith("http"):
                        continue
                    domain = urlparse(href).netloc.replace("www.", "")
                    if any(bad in domain for bad in IGNORE_DOMAINS):
                        continue

                    if any(dom in domain for dom in EVENT_DOMAINS):
                        meta = extract_external_metadata(href)
                        if meta["events"]:  # si c’est CGR avec séances
                            for s in meta["events"]:
                                results.append({
                                    "title": f"{s['film']} – Cinéma CGR Buxerolles",
                                    "description": ", ".join(s["horaires"]),
                                    "link": href,
                                    "source": "cgrcinemas.fr",
                                    "image": meta["image"],
                                    "location": "CGR Buxerolles",
                                    "address": address,
                                    "opening_hours": opening_hours
                                })
                        else:
                            results.append({
                                "title": meta["title"] or domain,
                                "description": meta["description"],
                                "link": href,
                                "source": domain,
                                "image": meta["image"],
                                "address": address,
                                "opening_hours": opening_hours
                            })

            except Exception as e:
                print(f"[VisitPoitiers] Erreur sur {link}: {e}")

    except Exception as e:
        print("[VisitPoitiers] ERREUR:", e)

    print(f"[VisitPoitiers] ✅ {len(results)} établissements/événements collectés (avec adresses et horaires)")
    return results


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
    print(f"💾 {len(dedup)} établissements/événements sauvegardés dans events.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
