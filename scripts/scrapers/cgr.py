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

        # Extraction des dates dans la section des jours (bandeau)
        days_section = soup.find("ul", class_="list-days") or soup.find("div", class_="list-days")
        days = []
        if days_section:
            for li in days_section.find_all(["li", "button", "a"]):
                label = li.get_text(strip=True)
                value = li.get("data-date") or li.get("href") or label
                if label:
                    days.append({"label": label, "value": value})
        else:
            print(f"⚠️ Aucune section de jours trouvée pour {cinema_name}")

        # Déterminer la date active (par défaut celle visible dans le HTML initial)
        active_day = None
        if days_section:
            active_li = days_section.find(class_="active") or days_section.find("li")
            if active_li:
                active_day = active_li.get("data-date") or active_li.get_text(strip=True)

        # Films visibles dans la page (correspondent au jour affiché par défaut)
        movies = soup.select(".movie-item, .movie-block")
        if not movies:
            print(f"⚠️ Aucun film trouvé pour {cinema_name}")
            continue

        for movie in movies:
            try:
                img_tag = movie.find("img")
                img_url = img_tag["src"] if img_tag else None

                title_tag = movie.find("h3") or movie.find("h2")
                title = title_tag.get_text(strip=True) if title_tag else "Inconnu"

                p_tag = movie.find("p")
                if p_tag:
                    meta_text = p_tag.get_text(" ", strip=True)
                    duration = meta_text.split("•")[0].strip() if "•" in meta_text else meta_text
                    description = meta_text.split("•")[-1].strip() if "•" in meta_text else ""
                else:
                    duration, description = "", ""

                # Extraction des horaires
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

                movie_data = {
                    "title": title,
                    "duration": duration,
                    "description": description,
                    "image": img_url,
                    "showtimes": showtimes,
                    "date": active_day or (days[0]["label"] if days else "Date inconnue"),
                    "cinema": cinema_name,
                    "source": url,
                    "scraped_at": datetime.now().isoformat()
                }

                all_movies.append(movie_data)

            except Exception as err:
                print(f"⚠️ Erreur sur un film ({cinema_name}): {err}")
                continue

    return all_movies


if __name__ == "__main__":
    data = scrape()
    print(f"✅ {len(data)} films trouvés")
    for d in data[:5]:
        print(f"- {d['title']} ({d['cinema']} - {d['date']}) : {len(d['showtimes'])} séances")
