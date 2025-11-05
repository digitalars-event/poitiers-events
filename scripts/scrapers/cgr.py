from playwright.sync_api import sync_playwright
import requests
import re
from datetime import datetime


CGR_CINEMAS = {
    "CGR Buxerolles": "https://www.cgrcinemas.fr/horaire-film/p0736-cgr-buxerolles-poitiers/",
    "CGR Castille": "https://www.cgrcinemas.fr/horaire-film/p0096-cgr-poitiers-castille/",
    "CGR Fontaine-le-Comte": "https://www.cgrcinemas.fr/horaire-film/w8624-cgr-fontaine-le-comte-poitiers/"
}


def extract_movie_ids_from_request(url: str):
    """Extrait tous les ids= depuis l'URL de la requête /movies"""
    return re.findall(r"ids=(\d+)", url)


def scrape_cinema(cinema_name, url):
    """Intercepte la requête /movies pour récupérer les IDs dynamiques"""
    print(f"\n🎬 {cinema_name}...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            movie_ids = []
            intercepted_url = None

            def on_request(request):
                nonlocal movie_ids, intercepted_url
                if "/api/gatsby-source-boxofficeapi/movies" in request.url:
                    intercepted_url = request.url
                    movie_ids = extract_movie_ids_from_request(request.url)

            page.on("request", on_request)

            try:
                # ✅ on attend seulement que le DOM soit prêt (pas le réseau complet)
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"⚠️ Erreur de navigation ({cinema_name}) : {e}")

            print("⏳ Attente du rendu dynamique (8s)...")
            page.wait_for_timeout(8000)

            # On capture le contenu pour déboguer au besoin
            current_url = page.url
            if "maintenance" in current_url.lower():
                print(f"⚠️ {cinema_name} redirigé vers maintenance ({current_url})")

            browser.close()

            if not intercepted_url or not movie_ids:
                print(f"⚠️ Aucune requête /movies interceptée pour {cinema_name}")
                return []

            print(f"✅ {len(movie_ids)} IDs détectés → {movie_ids[:5]}...")

            # --- Requête API directe ---
            params = [("ids", mid) for mid in movie_ids]
            res = requests.get(
                "https://www.cgrcinemas.fr/api/gatsby-source-boxofficeapi/movies",
                params=[("basic", "false"), ("castingLimit", "3")] + params,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=30
            )

            if res.status_code != 200:
                print(f"❌ Erreur API ({res.status_code}) pour {cinema_name}")
                return []

            data = res.json()
            movies = []

            for m in data:
                try:
                    duration_seconds = m.get("runtime") or 0
                    duration = f"{int(duration_seconds)//60} min" if duration_seconds else "Inconnue"

                    movies.append({
                        "title": m.get("title"),
                        "duration": duration,
                        "description": m.get("synopsis") or m.get("locale", {}).get("synopsis"),
                        "poster": m.get("poster"),
                        "genres": m.get("genres"),
                        "certificate": m.get("certificate"),
                        "release": m.get("release"),
                        "cinema": cinema_name,
                        "source": url,
                        "scraped_at": datetime.now().isoformat()
                    })
                except Exception as e:
                    print(f"⚠️ Erreur sur un film ({cinema_name}): {e}")
                    continue

            print(f"🎞️ {len(movies)} films récupérés pour {cinema_name}")
            return movies

    except Exception as e:
        print(f"❌ Erreur sur {cinema_name}: {e}")
        return []


def scrape():
    """Scrape tous les cinémas CGR avec interception dynamique"""
    all_movies = []
    for cinema_name, url in CGR_CINEMAS.items():
        all_movies += scrape_cinema(cinema_name, url)
    return all_movies


if __name__ == "__main__":
    data = scrape()
    print(f"\n💾 {len(data)} films sauvegardés dans events.json.")
    for m in data[:5]:
        print(f"- {m['title']} ({m['cinema']})")
