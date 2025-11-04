# scrapers/cgr.py
import requests
from bs4 import BeautifulSoup
from datetime import datetime

CGR_URLS = {
    "CGR Buxerolles": "https://www.cgrcinemas.fr/horaire-film/p0736-cgr-buxerolles-poitiers/",
    "CGR Castille": "https://www.cgrcinemas.fr/horaire-film/p0096-cgr-poitiers-castille/",
    "CGR Fontaine-le-Comte": "https://www.cgrcinemas.fr/horaire-film/w8624-cgr-fontaine-le-comte-poitiers/"
}

def scrape():
    all_movies = []

    for cinema_name, url in CGR_URLS.items():
        print(f"🎞️ Scraping {cinema_name}...")
        try:
            html = requests.get(url, timeout=20)
            html.raise_for_status()
        except Exception as e:
            print(f"❌ Erreur {cinema_name}: {e}")
            continue

        soup = BeautifulSoup(html.text, "html.parser")

        # Récupération du menu déroulant des dates
        date_select = soup.find("select", {"id": "select-date"})
        date_options = []
        if date_select:
            for opt in date_select.find_all("option"):
                value = opt.get("value")
                label = opt.text.strip()
                if value and label:
                    date_options.append({"date_value": value, "label": label})
        else:
            print(f"⚠️ Aucune date trouvée pour {cinema_name}")
            continue

        # Pour chaque date, charger les séances correspondantes
        for date_item in date_options:
            date_value = date_item["date_value"]
            label = date_item["label"]

            # Charger la page spécifique à cette date (URL avec ?date=)
            try:
                page = requests.get(f"{url}?date={date_value}", timeout=20)
                page.raise_for_status()
            except Exception as e:
                print(f"⚠️ Erreur chargement date {label} ({cinema_name}): {e}")
                continue

            day_soup = BeautifulSoup(page.text, "html.parser")
            movies = day_soup.select(".movie-item, .movie-block")

            for movie in movies:
                try:
                    # Image
                    img_tag = movie.find("img")
                    img_url = img_tag["src"] if img_tag else None

                    # Titre
                    title_tag = movie.find("h3") or movie.find("h2")
                    title = title_tag.get_text(strip=True) if title_tag else "Inconnu"

                    # Durée + Description
                    p_tag = movie.find("p")
                    if p_tag:
                        meta_text = p_tag.get_text(" ", strip=True)
                        duration = meta_text.split("•")[0].strip() if "•" in meta_text else meta_text
                        description = meta_text.split("•")[-1].strip() if "•" in meta_text else ""
                    else:
                        duration, description = "", ""

                    # Horaires
                    showtimes = []
                    for time_box in movie.select(".showtime, .hours, .session-item, .hour-item, .hour, .seance"):
                        text = time_box.get_text(strip=True)
                        if ":" in text:
                            showtimes.append(text)

                    if not showtimes:
                        for btn in movie.select("button"):
                            t = btn.get_text(strip=True)
                            if ":" in t:
                                showtimes.append(t)

                    # Ajout de la structure du film
                    movie_data = {
                        "title": title,
                        "duration": duration,
                        "description": description,
                        "image": img_url,
                        "showtimes": showtimes,
                        "date": label,
                        "cinema": cinema_name,
                        "source": url,
                        "scraped_at": datetime.now().isoformat()
                    }

                    all_movies.append(movie_data)

                except Exception as err:
                    print(f"⚠️ Erreur sur un film ({cinema_name}, {label}): {err}")
                    continue

    return all_movies


if __name__ == "__main__":
    data = scrape()
    print(f"✅ {len(data)} films trouvés")
    for d in data[:5]:
        print(f"- {d['title']} ({d['cinema']}, {d['date']}) : {len(d['showtimes'])} séances")
