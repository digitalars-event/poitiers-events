# scrapers/cgr.py
from playwright.sync_api import sync_playwright
import json
from datetime import datetime

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
            print(f"🎬 Chargement de {cinema_name}...")

            page = context.new_page()
            captured_json = []

            # Intercepter toutes les requêtes JSON vers les fichiers "page-data.json"
            def handle_response(response):
                if "page-data/films-a-l-affiche" in response.url and response.url.endswith("page-data.json"):
                    try:
                        data = response.json()
                        captured_json.append({"url": response.url, "data": data})
                    except Exception:
                        pass

            page.on("response", handle_response)

            # Charger la page et attendre que React ait fini
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(8000)

            if not captured_json:
                print(f"⚠️ Aucune requête JSON captée pour {cinema_name}")
                continue

            # Analyse du contenu JSON intercepté
            for capture in captured_json:
                data = capture["data"]
                result = data.get("result", {}).get("data", {})
                movie_info = result.get("movie")

                if not movie_info:
                    continue

                title = movie_info.get("title", "Inconnu")
                image = movie_info.get("poster")
                movie_id = movie_info.get("id")

                movie_entry = {
                    "id": movie_id,
                    "title": title,
                    "image": image,
                    "cinema": cinema_name,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "source": capture["url"],
                    "scraped_at": datetime.now().isoformat()
                }
                all_events.append(movie_entry)
                print(f"🎞️ {title} ({cinema_name}) ajouté")

        browser.close()

    return all_events


if __name__ == "__main__":
    movies = scrape()
    print(f"\n✅ {len(movies)} films trouvés")
    for m in movies[:5]:
        print(f"- {m['title']} ({m['cinema']})")
