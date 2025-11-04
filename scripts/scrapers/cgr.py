# scrapers/cgr.py
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
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
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                print("⏳ Attente du rendu React (5s)...")
                time.sleep(5)
                html = page.content()
            except Exception as e:
                print(f"⚠️ Erreur ouverture {cinema_name}: {e}")
                continue

            soup = BeautifulSoup(html, "html.parser")

            movies = soup.select("h2 a[href*='/films-a-l-affiche/']")
            print(f"🎞️ {len(movies)} films détectés pour {cinema_name}")

            for movie_link in movies:
                try:
                    title = movie_link.get_text(strip=True)
                    parent = movie_link.find_parent("div", class_="css-ygq8g8") or movie_link.find_parent("div")
                    
                    # Image (affiche)
                    img_tag = parent.find("img")
                    image = img_tag["src"] if img_tag else None

                    # Description et durée
                    p_tag = parent.find("p")
                    duration, description = "", ""
                    if p_tag:
                        text = p_tag.get_text(" ", strip=True)
                        parts = text.split("•")
                        if len(parts) >= 2:
                            duration = parts[0].strip()
                            description = parts[1].strip()
                        else:
                            description = text.strip()

                    # Horaires
                    showtimes = []
                    for tag in parent.select("button, div"):
                        text = tag.get_text(strip=True)
                        if ":" in text and len(text) <= 8:  # ex: 14h00, 22h15
                            showtimes.append(text)

                    movie_data = {
                        "title": title,
                        "duration": duration,
                        "description": description,
                        "image": image,
                        "showtimes": sorted(set(showtimes)),
                        "cinema": cinema_name,
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "source": url,
                        "scraped_at": datetime.now().isoformat()
                    }

                    all_events.append(movie_data)
                    print(f"✅ {title} ({cinema_name}) → {len(showtimes)} horaires")

                except Exception as e:
                    print(f"⚠️ Erreur parsing film ({cinema_name}) : {e}")
                    continue

        browser.close()

    return all_events


if __name__ == "__main__":
    data = scrape()
    print(f"\n💾 {len(data)} films sauvegardés.")
    for d in data[:5]:
        print(f"- {d['title']} ({d['cinema']}) : {len(d['showtimes'])} séances")
