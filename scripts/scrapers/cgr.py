# scrapers/cgr.py
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime

CGR_URLS = {
    "CGR Buxerolles": "https://www.cgrcinemas.fr/horaire-film/p0736-cgr-buxerolles-poitiers/",
    "CGR Castille": "https://www.cgrcinemas.fr/horaire-film/p0096-cgr-poitiers-castille/",
    "CGR Fontaine-le-Comte": "https://www.cgrcinemas.fr/horaire-film/w8624-cgr-fontaine-le-comte-poitiers/"
}

def scrape():
    all_movies = []

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()

        for cinema_name, url in CGR_URLS.items():
            print(f"🎬 Chargement de {cinema_name}...")
            page.goto(url, timeout=60000)
            page.wait_for_timeout(5000)  # attendre le rendu JS

            soup = BeautifulSoup(page.content(), "html.parser")

            # Extraction des films
            movies = soup.select(".movie-item, .movie-block")
            if not movies:
                print(f"⚠️ Aucun film trouvé pour {cinema_name}")
                continue

            for movie in movies:
                try:
                    title_tag = movie.find("h3") or movie.find("h2")
                    title = title_tag.get_text(strip=True) if title_tag else "Inconnu"

                    img_tag = movie.find("img")
                    img_url = img_tag["src"] if img_tag else None

                    p_tag = movie.find("p")
                    if p_tag:
                        meta_text = p_tag.get_text(" ", strip=True)
                        duration = meta_text.split("•")[0].strip() if "•" in meta_text else meta_text
                        description = meta_text.split("•")[-1].strip() if "•" in meta_text else ""
                    else:
                        duration, description = "", ""

                    showtimes = []
                    for time_box in movie.select(".showtime, .hours, .session-item, .hour-item, .hour, .seance, button"):
                        text = time_box.get_text(strip=True)
                        if ":" in text:
                            showtimes.append(text)

                    movie_data = {
                        "title": title,
                        "duration": duration,
                        "description": description,
                        "image": img_url,
                        "showtimes": showtimes,
                        "cinema": cinema_name,
                        "source": url,
                        "scraped_at": datetime.now().isoformat()
                    }
                    all_movies.append(movie_data)

                except Exception as err:
                    print(f"⚠️ Erreur sur un film ({cinema_name}): {err}")
                    continue

        browser.close()

    return all_movies


if __name__ == "__main__":
    data = scrape()
    print(f"✅ {len(data)} films trouvés")
    for d in data[:5]:
        print(f"- {d['title']} ({d['cinema']}) : {len(d['showtimes'])} séances")
