# scrapers/cgr.py
import requests
from datetime import datetime
import json

CGR_CINEMAS = {
    "CGR Buxerolles": "P0736",
    "CGR Castille": "P0096",
    "CGR Fontaine-le-Comte": "W8624",
}

# URL principale des APIs
BASE_API = "https://www.cgrcinemas.fr/api/gatsby-source-boxofficeapi"

# Liste d'IDs de films connus, utile comme fallback
DEFAULT_MOVIE_IDS = [
    "1000000149", "1000003120", "1000004239", "1000006191",
    "1000007022", "1000007239", "1000008466", "1000009081",
    "1000020329", "1000030333", "1000030655", "1000032312",
    "1000032450", "248289", "296641", "303027", "309613",
    "317579", "324790"
]


def get_movies(cinema_name, cinema_id):
    """Appelle l'API officielle CGR pour récupérer les films"""
    print(f"🎬 {cinema_name} – récupération des films en cours...")
    try:
        res = requests.get(
            f"{BASE_API}/movies",
            params={
                "basic": "false",
                "castingLimit": "3",
                **{f"ids": mid for mid in DEFAULT_MOVIE_IDS}
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/142.0.0.0 Safari/537.36"
            },
            timeout=30
        )

        if res.status_code != 200:
            print(f"⚠️ Erreur API {cinema_name} : {res.status_code}")
            return []

        movies = res.json()
        parsed = []

        for m in movies:
            parsed.append({
                "id": m.get("id"),
                "title": m.get("title"),
                "duration": f"{int(m.get('runtime', 0) // 60)} min",
                "genres": m.get("genres"),
                "synopsis": m.get("synopsis") or m.get("locale", {}).get("synopsis"),
                "poster": m.get("poster"),
                "studio": m.get("studio", {}).get("name"),
                "certificate": m.get("certificate"),
                "release_date": m.get("release"),
                "casting": [c.get("actor", {}).get("lastName") for c in m.get("cast", {}).get("nodes", [])],
                "director": [d.get("person", {}).get("lastName") for d in m.get("directors", {}).get("nodes", [])],
                "cinema": cinema_name,
                "source": "https://www.cgrcinemas.fr",
                "scraped_at": datetime.now().isoformat()
            })

        print(f"✅ {len(parsed)} films récupérés pour {cinema_name}")
        return parsed

    except Exception as e:
        print(f"❌ Erreur sur {cinema_name}: {e}")
        return []


def scrape():
    """Scrape tous les cinémas CGR configurés"""
    all_movies = []
    for cinema_name, cinema_id in CGR_CINEMAS.items():
        all_movies += get_movies(cinema_name, cinema_id)
    return all_movies


if __name__ == "__main__":
    movies = scrape()
    print(f"\n💾 {len(movies)} films trouvés.")
    print(json.dumps(movies[:3], indent=2, ensure_ascii=False))  # aperçu rapide
