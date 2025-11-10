# scrapers/tap.py
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re, html
from urllib.parse import urljoin

BASE_URL = "https://www.tap-poitiers.com"

# =========================================================
# 🎬 CINÉMA
# =========================================================
def scrape_cinema():
    """Scrape la liste des films TAP Cinéma + détail pour durée et description"""
    url = f"{BASE_URL}/cinema/"
    r = requests.get(url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    films = []

    for film in soup.select("article"):
        title_el = film.select_one("h2, h3, .title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        # Source (fiche du film)
        a = film.select_one("a")
        source = None
        if a and a.get("href"):
            href = a["href"]
            source = href if href.startswith("http") else BASE_URL + href

        # Poster
        poster = None
        img = film.select_one("img")
        if img and img.get("src"):
            src = img["src"]
            poster = src if src.startswith("http") else BASE_URL + src

        # --- Aller dans la fiche du film pour extraire durée et description ---
        duration = None
        description = None
        if source:
            try:
                detail_res = requests.get(source, timeout=10)
                if detail_res.ok:
                    detail_soup = BeautifulSoup(detail_res.text, "html.parser")

                    # Durée (ex : "Durée : 1h47")
                    dur_el = detail_soup.find(text=re.compile(r"Durée\s*:?"))
                    if dur_el:
                        match = re.search(r"(\d+h\d+|\d+h|\d+\s?min)", dur_el)
                        if match:
                            duration = match.group(1).replace(" ", "") + " min" if "min" not in match.group(1) else match.group(1)

                    # Description / synopsis
                    desc_el = detail_soup.select_one(".entry-content p, .article-content p")
                    if desc_el:
                        description = desc_el.get_text(strip=True)
            except Exception:
                pass

        films.append({
            "title": title,
            "duration": duration,
            "description": description,
            "poster": poster,
            "genres": None,
            "certificate": None,
            "release": None,
            "cinema": "TAP Cinéma Poitiers",
            "source": source,
            "scraped_at": datetime.utcnow().isoformat()
        })

    return films


# =========================================================
# 🎭 SPECTACLES
# =========================================================
def _extract_bg_url(style_value: str) -> str | None:
    """Extrait l'URL depuis un style background-image, gère &quot; et quotes."""
    if not style_value:
        return None
    style_value = html.unescape(style_value)
    m = re.search(r'url\(([^)]+)\)', style_value, flags=re.I)
    if not m:
        return None
    raw = m.group(1).strip().strip('\'"')
    return urljoin(BASE_URL, raw)

def _fallback_detail_image(detail_url: str) -> str | None:
    """Va sur la page détail pour récupérer og:image (fallback propre)."""
    try:
        r = requests.get(detail_url, timeout=10)
        if not r.ok:
            return None
        s = BeautifulSoup(r.text, "html.parser")
        og = s.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            return urljoin(BASE_URL, og["content"])
        img = s.select_one(".entry-content img, article img")
        if img and img.get("src"):
            return urljoin(BASE_URL, img["src"])
    except Exception:
        pass
    return None

def _is_placeholder(url: str | None) -> bool:
    if not url:
        return True
    return "themes/tap/images/template/default-image" in url


def scrape_spectacles():
    """Scrape la page des spectacles TAP avec images CSS + fallback og:image"""
    spectacles = []
    next_url = f"{BASE_URL}/spectacle/"

    while next_url:
        r = requests.get(next_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for block in soup.select(".grid-list .col-item"):
            # Image principale dans .grid-block__picture
            poster = None
            pic = block.select_one(".grid-block__picture")
            if pic and pic.get("style"):
                poster = _extract_bg_url(pic.get("style"))

            # Article lié
            article = block.select_one("article")
            if not article:
                continue

            # Titre + lien source
            title_el = article.select_one(".grid-block__title a, h2 a, h3 a")
            title = title_el.get_text(strip=True) if title_el else "Sans titre"
            href = title_el.get("href") if title_el else None
            source = urljoin(BASE_URL, href) if href else None

            # Date
            date_el = article.select_one("time.grid-block__date, .grid-block__date, time")
            date_text = date_el.get_text(" ", strip=True) if date_el else "Date à venir"

            # Reservation
            reservation = None
            res_a = article.select_one("a[href*='billet'], a[href*='ticket'], a[href*='resa']")
            if res_a and res_a.get("href"):
                reservation = urljoin(BASE_URL, res_a["href"])

            # Fallback si placeholder ou pas d'image
            if _is_placeholder(poster) and source:
                poster = _fallback_detail_image(source)

            spectacles.append({
                "title": title,
                "date": date_text,
                "release": None,
                "poster": poster,
                "cinema": "TAP Poitiers",
                "source": source,
                "reservation": reservation,
                "scraped_at": datetime.utcnow().isoformat()
            })

        # Pagination (si bouton "Voir plus")
        more_btn = soup.select_one(".load-more .bt-more[data-next]")
        next_url = more_btn.get("data-next") if more_btn else None

    return spectacles


# =========================================================
# 🔗 EXPORT PRINCIPAL
# =========================================================
def scrape_tap():
    """Combine cinéma + spectacle"""
    try:
        cinema = scrape_cinema()
    except Exception as e:
        print(f"⚠️  Erreur cinéma TAP : {e}")
        cinema = []

    try:
        spectacle = scrape_spectacles()
    except Exception as e:
        print(f"⚠️  Erreur spectacle TAP : {e}")
        spectacle = []

    return {"cinema": cinema, "spectacle": spectacle}
