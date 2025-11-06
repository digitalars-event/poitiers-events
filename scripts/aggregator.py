#!/usr/bin/env python3
# coding: utf-8

import json
from datetime import datetime, timezone

# --- Imports des scrapers ---
from scrapers import cgr, arena, republic_corner, parc_expo


def main():
    all_events = []

    # --- CGR ---
    #print("🎬 CGR...")
    #try:
    #    cgr_events = cgr.scrape()
    #    print(f"✅ {len(cgr_events)} événements récupérés depuis les cinémas CGR.")
    #    all_events += cgr_events
    #except Exception as e:
    #    print(f"❌ Erreur lors du scraping CGR : {e}")

    # --- ARENA ---
    #print("\n🎤 ARENA FUTUROSCOPE...")
    #try:
    #    arena_events = arena.scrape_arena()
    #    print(f"✅ {len(arena_events)} événements récupérés depuis l'Arena Futuroscope.")
    #    all_events += arena_events
    #except Exception as e:
    #    print(f"❌ Erreur lors du scraping Arena : {e}")

    # --- REPUBLIC CORNER ---
    #print("\n🎭 REPUBLIC CORNER...")
    #try:
    #    rc_events = republic_corner.scrape_republic_corner()
    #    print(f"✅ {len(rc_events)} événements récupérés depuis le Republic Corner.")
    #    all_events += rc_events
    #except Exception as e:
    #    print(f"❌ Erreur lors du scraping Republic Corner : {e}")

    # --- PARC EXPO GRAND POITIERS ---
    print("\n🏛️ PARC EXPO GRAND POITIERS...")
    try:
        expo_events = parc_expo.scrape_parc_expo()
        print(f"✅ {len(expo_events)} événements récupérés depuis le Parc Expo Grand Poitiers.")
        all_events += expo_events
    except Exception as e:
        print(f"❌ Erreur lors du scraping Parc Expo : {e}")

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

    # --- Tri chronologique robuste ---
    def parse_date(value):
        """Convertit n'importe quel format ISO en datetime naïf"""
        if not value:
            return datetime.max
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # Uniformise : si timezone présente, la convertir en UTC puis rendre naïve
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return datetime.max

    def sort_key(ev):
        return parse_date(ev.get("release")) or parse_date(ev.get("date"))

    unique.sort(key=sort_key)

    # --- Sauvegarde ---
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events": unique,
    }

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(
        f"\n💾 {len(unique)} événements sauvegardés dans events.json "
        f"({len(all_events)} collectés avant dédoublonnage)"
    )

    # --- Résumé final ---
    print("\n📊 RÉCAPITULATIF PAR SOURCE :")
    print(f"   🎬 CGR : {len(locals().get('cgr_events', []))}")
    print(f"   🎤 Arena : {len(locals().get('arena_events', []))}")
    print(f"   🎭 Republic Corner : {len(locals().get('rc_events', []))}")
    print(f"   🏛️ Parc Expo : {len(locals().get('expo_events', []))}")


if __name__ == "__main__":
    main()
