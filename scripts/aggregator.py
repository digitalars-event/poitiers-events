#!/usr/bin/env python3
# coding: utf-8

import json
from datetime import datetime, timezone

# --- Imports des scrapers ---
from scrapers import cgr, arena, republic_corner


def main():
    all_events = []

    # --- CGR ---
    print("🎬 CGR...")
    try:
        cgr_events = cgr.scrape()
        print(f"✅ {len(cgr_events)} événements récupérés depuis les cinémas CGR.")
        all_events += cgr_events
    except Exception as e:
        print(f"❌ Erreur lors du scraping CGR : {e}")

    # --- ARENA ---
    print("\n🎤 ARENA FUTUROSCOPE...")
    try:
        arena_events = arena.scrape_arena()
        print(f"✅ {len(arena_events)} événements récupérés depuis l'Arena Futuroscope.")
        all_events += arena_events
    except Exception as e:
        print(f"❌ Erreur lors du scraping Arena : {e}")

    # --- REPUBLIC CORNER ---
    print("\n🎭 REPUBLIC CORNER...")
    try:
        rc_events = republic_corner.scrape_republic_corner()
        print(f"✅ {len(rc_events)} événements récupérés depuis le Republic Corner.")
        all_events += rc_events
    except Exception as e:
        print(f"❌ Erreur lors du scraping Republic Corner : {e}")

    # --- Nettoyage des doublons ---
    seen = set()
    unique = []
    for ev in all_events:
        key = (
            ev.get("title", "").strip().lower(),
            ev.get("source", "").strip().lower(),
        )
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    # --- Tri chronologique (selon release/date ISO si dispo) ---
    def sort_key(ev):
        for k in ("release", "date"):
            if ev.get(k):
                try:
                    return datetime.fromisoformat(ev[k].replace("Z", "+00:00"))
                except Exception:
                    pass
        return datetime.max

    unique.sort(key=sort_key)

    # --- Sauvegarde ---
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events": unique,
    }

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 {len(unique)} événements sauvegardés dans events.json")


if __name__ == "__main__":
    main()
