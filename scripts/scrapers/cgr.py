# scrapers/cgr.py
import requests
from datetime import datetime

BASE_URL = "https://cms-assets.webediamovies.pro/prod/cgr/{date}/public/page-data/films-a-l-affiche"
TODAY = datetime.now().strftime("%Y-%m-%d")

def scrape():
    all_movies = []
    index_url = f"{BASE_URL.format(date=TODAY)}/page-data.json"

    print(f"🎬 Chargement de la liste des films pour le {TODAY}...")
    res = requests.get(index_url)
    if res.status_code != 200:
        print(f"❌ Impossible de récupérer la liste ({res.status_code})")
        return all_movies

    data = res.json()
    result = data.get("result", {}).get("data", {})

    # Cherche le bon noeud de films
    movies_nodes = []
    for key in result:
        if isinstance(result[key], dict) and "movies" in result[key]:
            movies_nodes = result[key]["movies"]
            break
        elif isinstance(result[key], list) and len(result[key]) and "title" in result[key][0]:
            movies_nodes = result[key]
            break

    if not movies_nodes:
        print("⚠️ Aucun film détecté dans la structure du JSON.")
        return all_movies

    for m in movies_nodes:
        try:
            title = m.get("title") or m.get("name")
            movie_id = m.get("id") or m.get("movieId")
            slug = m.get("slug") or f"{movie_id}-{title.lower().replace(' ', '-')}"
            image = m.get("poster") or m.get("image", {}).get("src")

            movie_url = f"{BASE_URL.format(date=TODAY)}/{slug}/page-data.json"

            all_movies.append({
                "id": movie_id,
                "title": title,
                "image": image,
                "url": movie_url,
                "date": TODAY,
                "source": "https://www.cgrcinemas.fr",
                "scraped_at": datetime.now().isoformat()
            })

            print(f"🎞️ {title} ajouté ({movie_id})")

        except Exception as e:
            print(f"⚠️ Erreur lecture film : {e}")
            continue

    return all_movies


if __name__ == "__main__":
    movies = scrape()
    print(f"\n✅ {len(movies)} films trouvés.")
    for m in movies[:5]:
        print(f"- {m['title']} ({m['url']})")
