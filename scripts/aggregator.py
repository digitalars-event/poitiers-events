#!/usr/bin/env python3
# coding: utf-8

import json
from datetime import datetime, timezone

from scrapers import cgr

def main():
    all_events = []

    print("🎬 CGR...")
    try:
        cgr_events = cgr.scrape()
        print(f"✅ {len(cgr_events)} événements récupérés depuis CGR.")
        all_events += cgr_events
    except Exception as e:
        print(f"❌ Erreur lors du scrapping CGR : {e}")

    # Nettoyage (doublons, tri)
    seen = set()
    unique = []
    for ev in all_events:
        key = (ev.get("title", "").strip().lower(), ev.get("source", "").strip().lower())
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    # Enregistrement
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events": unique
    }

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"💾 {len(unique)} événements sauvegardés dans events.json")

if __name__ == "__main__":
    main()
