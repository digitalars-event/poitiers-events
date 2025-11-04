# scrapers/cgr.py
from playwright.sync_api import sync_playwright
import requests, json
from datetime import datetime
from urllib.parse import urljoin

CGR_URLS = {
    "CGR Buxerolles": "https://www.cgrcinemas.fr/horaire-film/p0736-cgr-buxerolles-poitiers/",
    "CGR Castille": "https://www.cgrcinemas.fr/horaire-film/p0096-cgr-poitiers-castille/",
    "CGR Fontaine-le-Comte": "https://www.cgrcinemas.fr/horaire-film/w8624-cgr-fontaine-le-comte-poitiers/"
}

def scrape():
    all_events = []

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()

        for cinema_name, url in CGR_URLS.items():
            print(f"\n🎬 Analyse du site {cinema_name}...")
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(8000)
            except Exception as e:
                print(f"⚠️ Erreur ouverture page {cinema_name}: {e}")
                continue

            # Récupérer tous les liens "films à l’affiche"
            movie_links = page.locator("a[href*='/films-a-l-affiche/']").evaluate_all("els => els.map(e => e.getAttribute('href'))")
            print(f"🎞️ {len(movie_links)} liens de films trouvés pour {cinema_name}")

            for link in movie_links:
                if not link:
                    continue
                # Générer l’URL JSON Gatsby associée
                movie_json_url = link.replace("/films-a-l-affiche/", "/page-data/films-a-l-affiche/").rstrip("/") + "/page-data.json"
                movie_json_url = urljoin("https://cms-assets.webediamovies.pro/prod/cgr/", f"{datetime.now().strftime('%Y-%m-%d')}/public{movie_json_url}")
                
                try:
                    r = requests.get(movie_json_url, timeout=10)
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    movie = data.get("result", {}).get("data", {}).get("movie")
                    if not movie:
                        continue

                    title = movie.get("title", "Inconnu")
                    image = movie.get("poster")
                    movie_id = movie.get("id")

                    # Extraction simple des séances
                    showtimes = []
                    def extract_times(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if isinstance(v, str) and ":" in v:
                                    showtimes.append(v)
                                else:
                                    extract_times(v)
                        elif isinstance(obj, list):
                            for v in obj:
                                extract_times(v)

                    extract_times(movie.get("showtimes") or {})

                    all_events.append({
                        "id": movie_id,
                        "title": title,
                        "image": image,
                        "cinema": cinema_name,
                        "showtimes": sorted(set(showtimes)),
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "source": movie_json_url,
                        "scraped_at": datetime.now().isoformat()
                    })
                    print(f"✅ {title} ({cinema_name}) → {len(showtimes)} séances")
                except Exception as e:
                    print(f"⚠️ Erreur chargement {movie_json_url}: {e}")
                    continue

        browser.close()

    return all_events


if __name__ == "__main__":
    movies = scrape()
    print(f"\n💾 {len(movies)} films enregistrés.")
    for m in movies[:5]:
        print(f"- {m['title']} ({m['cinema']}) : {len(m['showtimes'])} séances")
