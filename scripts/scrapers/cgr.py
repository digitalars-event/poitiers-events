# scrapers/cgr.py
import requests
from datetime import datetime
from bs4 import BeautifulSoup

BASE_URL = "https://cms-assets.webediamovies.pro/prod/cgr/{date}/public/page-data/films-a-l-affiche"
TODAY = datetime.now().strftime("%Y-%m-%d")

def scrape():
    all_movies = []
    index_url = f"{BASE_URL.format(date=TODAY)}/page-data.json"

    print(f"🎬 Chargement de la liste des films pour le {TODAY}...")
    res = requests.get(index_url)
    if res.status_code != 200:
        print(f"❌ Impossible de récupérer la liste des films ({res.status_code})")
        return all_movies

    data = res.json()

    # extraction des liens vers les films individuels
    paths = []
    try:
        paths = [e["path"] for e in data["result"]["data"]["allSitePage"]["edges"]]
    except Exception:
        # fallback : recherche dans pageContext si le format diffère
        page_data = data.get("result", {}).get("pageContext", {})
        if page_data:
            paths.append(page_data.get("pagePath"))

    if not paths:
        print("⚠️ Aucun film trouvé dans l’index.")
        return all_movies

    for path in paths:
        if not path or not path.startswith("/films-a-l-affiche/"):
            continue

        movie_url = f"{BASE_URL.format(date=TODAY)}{path}/page-data.json"
        try:
            movie_res = requests.get(movie_url)
            movie_res.raise_for_status()
            movie_data = movie_res.json()

            movie_info = movie_data["result"]["data"]["movie"]
            title = movie_info.get("title", "Inconnu")
            image = movie_info.get("poster")
            movie_id = movie_info.get("id")

            # construire la structure
            movie_entry = {
                "id": movie_id,
                "title": title,
                "image": image,
                "date": TODAY,
                "source": movie_url,
                "scraped_at": datetime.now().isoformat()
            }

            all_movies.append(movie_entry)
            print(f"🎞️ {title} ajouté ({movie_id})")

        except Exception as e:
            print(f"⚠️ Erreur lors du chargement de {movie_url} : {e}")
            continue

    return all_movies


if __name__ == "__main__":
    movies = scrape()
    print(f"\n✅ {len(movies)} films trouvés.")
    for m in movies[:5]:
        print(f"- {m['title']} ({m['id']})")
