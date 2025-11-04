#!/usr/bin/env python3
# coding: utf-8

import json
from datetime import datetime, timezone

from scrapers import cgr, tap, republic_corner, la_quintaine, futuroscope

def main():
    all_events = []

    print("🎬 CGR...")
    all_events += cgr.scrape()

    print("🎭 TAP...")
    all_events += tap.scrape()

    print("🎶 Republic Corner...")
    all_events += republic_corner.scrape()

    print("🏛️ La Quintaine...")
    all_events += la_quintaine.scrape()

    print("🚀 Futuroscope...")
    all_events += futuroscope.scrape()

    # Nettoyage (doublons, tri)
    seen = set()
    unique = []
    for ev in all_events:
        key = (ev.get("title","").lower(), ev.get("source","").lower())
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    # Enregistrement
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "events": unique
        }, f, ensure_ascii=False, indent=2)

    print(f"💾 {len(unique)} événements sauvegardés dans events.json")

if __name__ == "__main__":
    main()
