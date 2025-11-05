#!/usr/bin/env python3
# coding: utf-8

import json
from datetime import datetime, timezone

# --- Import du scraper Republic Corner ---
from scrapers import republic_corner

def main():
    all_events = []

    # --- REPUBLIC CORNER ---
    print("🎭 REPUBLIC CORNER...")
    try:
        rc_events = republic_corner.scrape_republic_corner()
        print(f"✅ {len(rc_events)} événements récupérés depuis le Republic Corner.")
        all_events += rc_events
    except Exception as e:
        print(f"❌ Erreur lors du scraping Republic Corner : {e}")

    # --- Nettoyage (doublons, tri) ---
    seen = set()
    unique = []
    for ev in all_events:
        key = (ev.get("title", "").strip().lower(), ev.get("source", "").strip().lower())
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    # --- Tri par date (si dispo) ---
    def sort_key(ev):
        try:
            # On privilégie release (format ISO) si présent, sinon la date brute
            return ev.get("release") or ev.get("date") or ""
        except Exception:
            return ""

    unique.sort(key=sort_key)

    # --- Sauvegarde ---
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events": unique
    }

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 {len(unique)} événements sauvegardés dans events.json")


if __name__ == "__main__":
    main()
