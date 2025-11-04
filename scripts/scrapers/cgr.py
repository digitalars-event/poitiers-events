# scrapers/cgr.py
import requests
from datetime import datetime

CGR_CINEMAS = {
    "CGR Buxerolles": "P0736",
    "CGR Castille": "P0096",
    "CGR Fontaine-le-Comte": "W8624",
}

BASE_API = "https://www.cgrcinemas.fr/api/gatsby-source-boxofficeapi/movies"

def get_movies_for(cinema_id, cinema_name):
    """Récupère les films à l'affiche pour un cinéma CGR donné"""
    try:
        # On récupère d’abord la liste des IDs de films via la page JSON du cinéma
        index_url = f"https://www.cgrcinemas.fr/page-data/horaire-film/{cinema_id.lower()}-page-data.json"
        res = requests.get(index_url)
        if res.status_code != 200:
            print(f"⚠️ Impossible d'obtenir la page {cinema_name} ({res.status_code})")
            return []

        data = res.json()
        movies = []

        # Extraction des IDs de films visibles dans la structure Gatsby
        movie_ids = []
        for key, value in data.get("result", {}).get("data", {}).items():
            if isinstance(value, list):
                for v in value:
                    if isinstance(v, dict) and "id" in v:
                        movie_ids.append(v["id"])

        # Si pas d’IDs trouvés → fallback sur API standard de CGR avec les plus récents
        if not movie_ids:
            print(f"⚠️ Aucun ID trouvé pour {cinema_name}, utilisation d’un fallback")
            movie_ids = [
                "278666", "1000014949", "1000009067", "308151", "321151"
            ]  # tu peux les remplacer par un fetch dynamique

        params = {
            "basic": "false",
            "castingLimit": "3",
        }
        for mid in movie_ids:
            params["ids"] = movie_ids

        res = requests.get(BASE_API, params=params)
        if res.status_code != 200:
            print(f"⚠️ Erreur API CGR ({cinema_name}) : {res.status_code}")
            return []

        movies_json = res.json()
        result = []

        for m in movies_json:
            movie_data = {
                "title": m.get("title"),
                "duration": f"{int(m.get('runtime', 0)//60)} min",
                "description": m.get("synopsis") or m.get("locale", {}).get("synopsis"),
                "image": m.get("poster"),
                "genres": m.get("genres"),
                "release": m.get("release"),
                "certificate": m.get("certificate"),
                "cinema": cinema_name,
                "source": "https://www.cgrcinemas.fr",
                "scraped_at": datetime.now().isoformat(),
            }
            result.append(movie_data)

        print(f"🎞️ {len(result)} films récupérés pour {cinema_name}")
        return result

    except Exception as e:
        print(f"❌ Erreur sur {cinema_name}: {e}")
        return []


def scrape():
    """Récupère tous les films des 3 CGR"""
    all_movies = []
    for cinema_name, cinema_id in CGR_CINEMAS.items():
        print(f"\n🎬 {cinema_name}...")
        all_movies += get_movies_for(cinema_id, cinema_name)
    return all_movies


if __name__ == "__main__":
    movies = scrape()
    print(f"\n✅ Total: {len(movies)} films")
    for m in movies[:5]:
        print(f"- {m['title']} ({m['cinema']})")
