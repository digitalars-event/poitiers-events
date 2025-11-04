# scrapers/cgr.py
from playwright.sync_api import sync_playwright
import json
from datetime import datetime
import time

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
            print(f"\n🎬 Chargement de {cinema_name}...")
            page = context.new_page()
            captured_json = []

            def handle_response(response):
                if "page-data.json" in response.url and any(
                    key in response.url for key in ["films-a-l-affiche", "horaires"]
                ):
                    try:
                        data = response.json()
                        captured_json.append({"url": response.url, "data": data})
                    except Exception:
                        pass

            page.on("response", handle_response)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Laisser le JS charger les données
                print("⏳ Attente du rendu complet (React)...")
                time.sleep(12)
            except Exception as e:
                print(f"⚠️ Erreur initiale ({cinema_name}) : {e}")
                continue

            if not captured_json:
                print(f"⚠️ Aucune requête JSON captée pour {cinema_name}")
                continue

            for capture in captured_json:
                data = capture["data"].get("result", {}).get("data", {})
                movie = data.get("movie")
                if not movie:
                    continue

                title = movie.get("title", "Inconnu")
                image = movie.get("poster")
                movie_id = movie.get("id")

                showtimes_data = movie.get("showtimes") or movie.get("schedules") or {}
                showtimes = []

                def extract_times(obj, date_key=None):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if "time" in k and isinstance(v, str):
                                showtimes.append(f"{date_key or ''} {v}".strip())
                            elif "date" in k and isinstance(v, str):
                                extract_times(v, v)
                            else:
                                extract_times(v, date_key)
                    elif isinstance(obj, list):
                        for v in obj:
                            extract_times(v, date_key)

                extract_times(showtimes_data)

                movie_entry = {
                    "id": movie_id,
                    "title": title,
                    "image": image,
                    "cinema": cinema_name,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "showtimes": sorted(set(showtimes)),
                    "source": capture["url"],
                    "scraped_at": datetime.now().isoformat()
                }

                all_events.append(movie_entry)
                print(f"🎞️ {title} ({cinema_name}) → {len(showtimes)} séances")

        browser.close()

    return all_events


if __name__ == "__main__":
    movies = scrape()
    print(f"\n✅ {len(movies)} films trouvés.")
    for m in movies[:5]:
        print(f"- {m['title']} ({m['cinema']}) : {len(m['showtimes'])} séances")
