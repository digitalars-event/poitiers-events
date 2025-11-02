#!/usr/bin/env python3
# coding: utf-8
"""
Agrégateur d'événements Poitiers (avec scraping VisitPoitiers.fr approfondi)
- Récupère les vraies dates des événements ("du ... au ...")
- Extrait correctement les images (Open Graph, images principales ou CSS)
- Filtre les événements passés
- Scrape aussi les liens externes d'événements (Facebook, Billetweb, etc.) présents sur les pages d'établissements
"""

import os, sys, json, re, traceback, time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin
import requests
from dateutil import parser as dp
from bs4 import BeautifulSoup

CITY = "Poitiers"
TODAY_UTC = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
VISITPOITIERS_BASE = "https://visitpoitiers.fr"

# Liste des domaines considérés comme sources d'événements externes
EVENT_DOMAINS = [
    "facebook.com",
    "weezevent.com",
    "billetweb.fr",
    "eventbrite.fr",
    "helloasso.com",
    "yurplan.com"
]

# --- UTILS ---
def parse_date(text) -> Optional[datetime]:
    """Convertit un texte en datetime UTC, ou None."""
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
    return f"{norm_text(ev.get('title','')).lower()}::{norm_text(ev.get('location','')).lower()}"


def clamp_len(s: str, n: int):
    s = s or ""
    return (s[:n-1] + "…") if len(s) > n else s


# --- MAIN SCRAPER ---
def fetch_visitpoitiers():
    print("[VisitPoitiers] Scraping depuis le plan du site (avec événements externes)…")
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
                r2 = requests.get(link, timeout=15)
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
                else:
                    img_tag = soup2.select_one(".wp-post-image, .elementor-image img, article img, main img")
                    if img_tag and img_tag.get("src"):
                        src = img_tag["src"]
                        if not any(bad in src for bad in ["facebook.com/tr", "analytics", "1x1", "pixel"]):
                            image_url = urljoin(link, src)

                # --- DATES ---
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

                # --- FILTRE DES ÉVÉNEMENTS PASSÉS ---
                if date_end and date_end < TODAY_UTC:
                    continue
                if date_start and not date_end and date_start < TODAY_UTC:
                    continue

                # --- ÉVÉNEMENT PRINCIPAL ---
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

                # --- EXTRACTION DES ÉVÉNEMENTS EXTERNES (Facebook, Billetweb...) ---
                external_links = [
                    a["href"] for a in soup2.select("a[href]")
                    if any(domain in a["href"] for domain in EVENT_DOMAINS)
                ]

                for ext in external_links:
                    ev_ext = {
                        "title": f"Événement externe lié à {title}",
                        "location": address or "Grand Poitiers",
                        "link": ext,
                        "source": "visitpoitiers-lien-externe",
                        "parent": title,
                        "description": f"Événement référencé via la page de {title}",
                        "image": image_url or ""
                    }
                    events.append(ev_ext)

            except Exception as e:
                print(f"[VisitPoitiers] Erreur sur {link}: {e}")

    except Exception as e:
        print("[VisitPoitiers] ERREUR sur le plan du site:", e)

    print(f"[VisitPoitiers] ✅ {len(events)} éléments collectés (y compris événements externes à venir)")
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
    print(f"\n💾 {len(dedup)} éléments écrits dans events.json (y compris événements externes)")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
