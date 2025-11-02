#!/usr/bin/env python3
# coding: utf-8
"""
Agrégateur d'événements Poitiers (avec scraping VisitPoitiers.fr approfondi)
- Récupère les vraies dates des événements ("du ... au ...")
- Extrait correctement les images (Open Graph, images principales ou CSS)
- Filtre les événements passés
- Scrape aussi les liens externes d'événements (Facebook, Billetweb, etc.)
  et récupère automatiquement leurs métadonnées
"""

import os, sys, json, re, traceback, time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse
import requests
from dateutil import parser as dp
from bs4 import BeautifulSoup

CITY = "Poitiers"
TODAY_UTC = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
VISITPOITIERS_BASE = "https://visitpoitiers.fr"

# Domaines considérés comme plateformes d'événements
EVENT_DOMAINS = [
    "facebook.com",
    "weezevent.com",
    "billetweb.fr",
    "eventbrite.fr",
    "helloasso.com",
    "yurplan.com"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PoitiersScraper/1.0; +https://visitpoitiers.fr)"
}

# --- UTILS ---
def parse_date(text) -> Optional[datetime]:
    if not text:
        return None
    try:
        dt = dp.parse(str(text), dayfirst=True, fuzzy=True)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def dedup_key(ev):
    return f"{norm_text(ev.get('title','')).lower()}::{norm_text(ev.get('link','')).lower()}"


def clamp_len(s: str, n: int):
    s = s or ""
    return (s[:n-1] + "…") if len(s) > n else s


# --- EXTRACT META FROM EXTERNAL LINK ---
def extract_external_metadata(url: str) -> dict:
    """Récupère les métadonnées (title, desc, image, date) d'un lien externe."""
    meta = {
        "title": None,
        "description": None,
        "image": None,
        "date_start": None
    }

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if "text/html" not in r.headers.get("Content-Type", ""):
            return meta

        soup = BeautifulSoup(r.text, "html.parser")

        # --- Titre ---
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            meta["title"] = norm_text(og_title["content"])
        elif soup.title:
            meta["title"] = norm_text(soup.title.text)

        # --- Description ---
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            meta["description"] = norm_text(og_desc["content"])
        else:
            desc_tag = soup.find("meta", attrs={"name": "description"})
            if desc_tag and desc_tag.get("content"):
                meta["description"] = norm_text(desc_tag["content"])

        # --- Image ---
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            meta["image"] = og_image["content"]

        # --- Date ---
        # Recherche simple d'une date dans le texte (format jour/mois/année)
        text = soup.get_text(" ", strip=True)
        m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text)
        if m:
            meta["date_start"] = parse_date(m.group(1))

    except Exception as e:
        print(f"[META] Erreur sur {url}: {e}")

    return meta


# --- SCRAPER PRINCIPAL ---
def fetch_visitpoitiers():
    print("[VisitPoitiers] Scraping depuis le plan du site (avec liens externes enrichis)…")
    sitemap_url = f"{VISITPOITIERS_BASE}/plan-du-site/"
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
            time.sleep(0.4)

            try:
                r2 = requests.get(link, headers=HEADERS, timeout=15)
                if "text/html" not in r2.headers.get("Content-Type", ""):
                    continue
                soup2 = BeautifulSoup(r2.text, "html.parser")

                # --- TITRE ---
                title_tag = soup2.find("h1")
                title = title_tag.get_text(strip=True) if title_tag else link.split("/")[-2].replace("-", " ").title()

                # --- DESCRIPTION ---
                desc_tag = soup2.find("p")
                desc = desc_tag.get_text(strip=True) if desc_tag else ""

                # --- ADRESSE ---
                address = ""
                for p in soup2.find_all("p"):
                    if any(v in p.text for v in ["Poitiers", "Saint-Benoît", "Chauvigny", "Ligugé", "Chasseneuil"]):
                        address = norm_text(p.text)
                        break

                # --- IMAGE ---
                image_url = None
                og_tag = soup2.find("meta", property="og:image")
                if og_tag and og_tag.get("content"):
                    image_url = urljoin(link, og_tag["content"])

                # --- DATES ("du ... au ...") ---
                date_start, date_end = None, None
                date_section = soup2.select_one(".lesdates h2")
                if date_section:
                    text = norm_text(date_section.get_text(" ", strip=True))
                    match = re.search(r"du\s+([\d/]+).*?au\s+([\d/]+)", text, re.I)
                    if match:
                        date_start = parse_date(match.group(1))
                        date_end = parse_date(match.group(2))
                    else:
                        m2 = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", text)
                        if m2:
                            date_start = parse_date(m2.group(1))

                # --- TYPE ---
                is_event = "/evenement/" in link
                source_type = "visitpoitiers-evenement" if is_event else "visitpoitiers-activite"

                # --- FILTRAGE DES ÉVÉNEMENTS PASSÉS ---
                if date_end and date_end < TODAY_UTC:
                    continue
                if date_start and not date_end and date_start < TODAY_UTC:
                    continue

                # --- ENREGISTREMENT DE L'ÉVÉNEMENT PRINCIPAL ---
                ev = {
                    "title": clamp_len(title, 220),
                    "location": address or "Grand Poitiers",
                    "link": link,
                    "source": source_type,
                    "description": norm_text(desc),
                    "image": image_url or ""
                }

                if date_start:
                    ev["date_start"] = date_start.isoformat()
                if date_end:
                    ev["date_end"] = date_end.isoformat()

                events.append(ev)

                # --- EXTRACTION DES LIENS EXTERNES ---
                for a in soup2.select("a[href]"):
                    href = a["href"]
                    if not any(domain in href for domain in EVENT_DOMAINS):
                        continue

                    domain = urlparse(href).netloc.replace("www.", "")
                    meta = extract_external_metadata(href)
                    time.sleep(0.6)

                    ev_ext = {
                        "title": meta["title"] or f"Événement sur {domain}",
                        "location": address or CITY,
                        "link": href,
                        "source": domain,
                        "parent": title,
                        "description": meta["description"] or f"Événement référencé via {title}",
                        "image": meta["image"] or image_url or ""
                    }

                    if meta["date_start"]:
                        ev_ext["date_start"] = meta["date_start"].isoformat()

                    # Filtrage des passés
                    if "date_start" in ev_ext:
                        d = parse_date(ev_ext["date_start"])
                        if d and d < TODAY_UTC:
                            continue

                    events.append(ev_ext)

            except Exception as e:
                print(f"[VisitPoitiers] Erreur sur {link}: {e}")

    except Exception as e:
        print("[VisitPoitiers] ERREUR sur le plan du site:", e)

    print(f"[VisitPoitiers] ✅ {len(events)} éléments collectés (y compris événements externes enrichis)")
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

    print(f"\n💾 {len(dedup)} éléments écrits dans events.json (internes + externes enrichis)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
