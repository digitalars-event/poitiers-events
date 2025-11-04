# scrapers/cgr.py
from playwright.sync_api import sync_playwright
import time, json
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
            print(f"\n🎬 Chargement de {cinema_name}...")
            page = context.new_page()
            captured_json = []

            def handle_response(response):
                if "page-data/films-a-l-affiche" in response.url and response.url.endswith("page-data.json"):
                    try:
                        data = response.json()
                        captured_json.append({"url": response.url, "data": data})
                    except Exception:
                        pass

            page.on("response", handle_response)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            # Récupérer tous les liens de films sur la page
            movie_links = page.locator("a[href*='/films-a-l-affiche/']").all()
            print(f"🎞️ {len(movie_links)} films détectés sur la page")

            for i, link in enumerate(movie_links[:20]):  # limite à 20 pour éviter les boucles infinies
                try:
                    href = link.get_attribute("href")
                    if not href:
                        continue
                    print(f"➡️ Ouverture du film {i+1}/{len(movie_links)} : {href}")
                    page.goto("https://www.cgrcinemas.fr" + href, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)
                except Exception as e:
                    print(f"⚠️ Erreur navigation film : {e}")
                    continue

            if not captured_json:
                print(f"⚠️ Aucune requête JSON interceptée pour {cinema_name}")
                continue

            # Traitement des données interceptées
            for capture in captured_json:
                data = capture["data"].get("result", {}).get("data", {})
                movie = data.get("movie")
                if not movie:
                    continue

                title = movie.get("title", "Inconnu")
                image = movie.get("poster")
                movie_id = movie.get("id")

                # Extraction simple des séances
                showtimes_data = movie.get("showtimes") or {}
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

                extract_times(showtimes_data)

                movie_entry = {
                    "id": movie_id,
                    "title": title,
                    "image": image,
                    "cinema": cinema_name,
                    "showtimes": sorted(set(showtimes)),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "source": capture["url"],
                    "scraped_at": datetime.now().isoformat()
                }

                all_events.append(movie_entry)
                print(f"✅ {title} ({cinema_name}) → {len(showtimes)} séances")

        browser.close()

    return all_events


if __name__ == "__main__":
    data = scrape()
    print(f"\n💾 {len(data)} films sauvegardés.")
    for d in data[:5]:
        print(f"- {d['title']} ({d['cinema']}) : {len(d['showtimes'])} séances")
