import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import re
import locale

# Force locale française (si dispo)
try:
    locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")
except:
    pass


def normalize_date_from_text(date_text: str):
    """Convertit une date française complète en ISO 8601."""
    if not date_text:
        return None

    months = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
    }

    # Ex: "vendredi 14 novembre 2025"
    m = re.search(r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", date_text.lower())
    if not m:
        return None

    day, month_str, year = int(m.group(1)), m.group(2), int(m.group(3))
    month = months.get(month_str)
    if not month:
        return None

    try:
        return datetime(year, month, day, 20, 0, 0).isoformat()
    except Exception:
        return None


def normalize_date(day_text: str, month_text: str):
    """Convertit un jour et un mois français en date ISO (page principale)."""
    if not day_text or not month_text:
        return None

    months = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
    }

    if "jusqu" in day_text.lower() or "partir" in day_text.lower():
        return None

    m = re.search(r"(\d{1,2})", day_text)
    if not m:
        return None

    day = int(m.group(1))
    month = months.get(month_text.lower())
    if not month:
        return None

    now = datetime.now()
    year = now.year
    if month < now.month - 3:
        year += 1

    try:
        dt = datetime(year, month, day, 20, 0, 0)
        return dt.isoformat()
    except Exception:
        return None


def fetch_date_from_detail_page(url):
    """Va chercher la date complète sur la page d’un événement."""
    try:
        r = requests.get(url, timeout=10)
        if not r.ok:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        date_cell = soup.select_one("table.nano_01 td.nano_01_:nth-of-type(2)")
        if date_cell:
            full_date = date_cell.get_text(strip=True)
            iso_date = normalize_date_from_text(full_date)
            return full_date, iso_date
    except Exception:
        return None, None
    return None, None


def scrape_confort_moderne():
    url = "https://www.confort-moderne.fr/fr/agenda/details"
    events = []

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        rows = soup.select("tr.tr-table")
        current_month = None

        for row in rows:
            cols = row.find_all("td")
            if not cols:
                continue

            # --- Mois (souvent 1ère colonne, ex: NOVEMBRE, DÉCEMBRE)
            month_td = cols[0]
            if month_td and month_td.get_text(strip=True):
                current_month = month_td.get_text(strip=True)

            # --- Date / période
            date_td = cols[1] if len(cols) > 1 else None
            date_text = date_td.get_text(" ", strip=True) if date_td else ""

            # --- Image (fond de div.img_filter)
            img_td = row.select_one("td.img-table .img_filter")
            poster = None
            if img_td and "background-image" in img_td.get("style", ""):
                match = re.search(r"url\(['\"]?(.*?)['\"]?\)", img_td["style"])
                if match:
                    poster = match.group(1)

            # --- Titre et description (artistes)
            title_td = row.select_one("td a.clic")
            title = title_td.get_text(strip=True) if title_td else "Sans titre"
            description_span = row.select_one("td span span")
            description = description_span.get_text(strip=True) if description_span else None

            # --- Type (Concert, Expo...)
            type_td = cols[-2] if len(cols) >= 5 else None
            type_event = type_td.get_text(strip=True) if type_td else None

            # --- Lieu (dernière colonne souvent)
            location_td = cols[-1] if len(cols) >= 6 else None
            location = location_td.get_text(strip=True) if location_td else "Confort Moderne, Poitiers"

            # --- Lien source (onclick ou <a>)
            onclick = row.get("onclick")
            if onclick and "location.href=" in onclick:
                match = re.search(r"location\.href='(.*?)'", onclick)
                source = match.group(1) if match else url
            else:
                link_tag = row.select_one("a.clic")
                source = link_tag["href"] if link_tag and "href" in link_tag.attrs else url

            # --- Concatène mois + jour
            full_date = f"{current_month or ''} {date_text}".strip()
            iso_date = normalize_date(date_text, current_month or "")

            # --- Si la date n’est pas exploitable, on va sur la page détail
            if not iso_date:
                full_date_detail, iso_date_detail = fetch_date_from_detail_page(source)
                if iso_date_detail:
                    full_date = full_date_detail
                    iso_date = iso_date_detail

            # --- Enregistrement
            events.append({
                "title": title,
                "date": full_date,
                "release": iso_date,
                "poster": poster,
                "description": description,
                "cinema": "Confort Moderne",
                "type": type_event,
                "location": location,
                "source": source,
                "scraped_at": datetime.now().isoformat()
            })

        # ✅ Supprime les doublons sans changer l’ordre
        seen = set()
        unique = []
        for ev in events:
            key = (ev["title"].lower(), ev["source"].lower())
            if key not in seen:
                seen.add(key)
                unique.append(ev)

        print(f"🎸 Confort Moderne : {len(unique)} événements collectés (ordre préservé)")
        return unique

    except Exception as e:
        print(f"❌ Erreur lors du scraping Confort Moderne : {e}")
        return []


if __name__ == "__main__":
    data = scrape_confort_moderne()
    output = {
        "generated_at": datetime.now().isoformat(),
        "events": data
    }

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("💾 Données sauvegardées dans events.json")
