#!/usr/bin/env python3
# coding: utf-8

import json
from datetime import datetime, timezone

# --- Imports des scrapers ---
from scrapers import cgr, arena, republic_corner, parc_expo, tap, confort_moderne, m3q


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

    # --- ARENA FUTUROSCOPE ---
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

    # --- PARC EXPO GRAND POITIERS ---
    print("\n🏛️ PARC EXPO GRAND POITIERS...")
    try:
        expo_events = parc_expo.scrape_parc_expo()
        print(f"✅ {len(expo_events)} événements récupérés depuis le Parc Expo Grand Poitiers.")
        all_events += expo_events
    except Exception as e:
        print(f"❌ Erreur lors du scraping Parc Expo : {e}")

    # --- TAP POITIERS ---
    print("\n🎭 TAP POITIERS...")
    try:
        tap_data = tap.scrape_tap()
        cinema_events = tap_data.get("cinema", [])
        spectacle_events = tap_data.get("spectacle", [])
        total_tap = len(cinema_events) + len(spectacle_events)
        print(f"✅ {total_tap} événements récupérés depuis le TAP Poitiers ({len(cinema_events)} cinéma, {len(spectacle_events)} spectacles).")
        all_events += cinema_events + spectacle_events
    except Exception as e:
        print(f"❌ Erreur lors du scraping TAP Poitiers : {e}")

    # --- CONFORT MODERNE ---
    print("\n🎸 CONFORT MODERNE...")
    try:
        confort_events = confort_moderne.scrape_confort_moderne()
        print(f"✅ {len(confort_events)} événements récupérés depuis le Confort Moderne.")
        all_events += confort_events
    except Exception as e:
        print(f"❌ Erreur lors du scraping Confort Moderne : {e}")

    # --- Maison des 3 quartiers ---
    print("\n🏡 MAISON DES 3 QUARTIERS (M3Q)...")
    try:
        m3q_events = m3q.scrape_m3q()
        print(f"✅ {len(m3q_events)} événements récupérés depuis la M3Q.")
        all_events += m3q_events
    except Exception as e:
        print(f"❌ Erreur lors du scraping M3Q : {e}")

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
        if not value:
            return datetime.max
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
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
    print(f"   🎭 TAP Poitiers : {len(locals().get('cinema_events', [])) + len(locals().get('spectacle_events', []))}")
    print(f"   🎸 Confort Moderne : {len(locals().get('confort_events', []))}")
    print(f"   🎬 M3Q : {len(locals().get('m3q_events', []))}")


if __name__ == "__main__":
    main()
