import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

URL = "https://m3q.centres-sociaux.fr/saison-culturelle-2025-26/"


# --- Convertit une date FR en ISO ---
def convert_to_iso(text_date, text_time=None):
    # Exemple d'entrée :
    # "VENDREDI 10 OCTOBRE"
    # "Samedi 14 mars / 20h30"

    mois = {
        "JANVIER": "01", "FÉVRIER": "02", "FEVRIER": "02",
        "MARS": "03", "AVRIL": "04", "MAI": "05", "JUIN": "06",
        "JUILLET": "07", "AOÛT": "08", "AOUT": "08",
        "SEPTEMBRE": "09", "OCTOBRE": "10",
        "NOVEMBRE": "11", "DÉCEMBRE": "12", "DECEMBRE": "12"
    }

    text_date = text_date.upper().replace("1ER", "1")

    # Extraction du jour + mois
    match = re.search(r"(\d{1,2})\s+([A-ZÉÈÊÎÔÛÀÙÂÇ]+)", text_date)
    if not match:
        return None

    jour = match.group(1)
    mois_txt = match.group(2)

    if mois_txt not in mois:
        return None

    mois_num = mois[mois_txt]

    année = "2025"  # saison 2025-2026

    # Heure
    if text_time:
        # Ex: "20h30"
        m_time = re.search(r"(\d{1,2})h(\d{2})", text_time)
        if m_time:
            h = m_time.group(1)
            m = m_time.group(2)
        else:
            h, m = "00", "00"
    else:
        h, m = "00", "00"

    iso = f"{année}-{mois_num}-{int(jour):02d}T{h}:{m}:00Z"
    return iso


def scrape_m3q():
    response = requests.get(URL, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    events = []
    sections = soup.find_all("section", class_="elementor-section")

    current_date = None

    for section in sections:

        # --- TITRE DE DATE ---
        date_block = section.find("p")
        if date_block:
            txt = date_block.get_text(strip=True).upper()
            if txt.startswith(("LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE")):
                current_date = txt
                continue

        # --- BLOC ÉVÈNEMENT ---
        image = section.find("img")
        title = section.find("h4")
        texts = section.find_all("div", class_="elementor-widget-container")

        if not (image and title and current_date):
            continue

        image_url = image["src"]
        event_title = title.get_text(strip=True)

        subtitle = None
        description_parts = []
        time_info = None

        # Extraction des blocs texte
        for t in texts:
            content = t.get_text("\n", strip=True).strip()

            # Sous-titre
            if content.startswith("·"):
                subtitle = content.replace("·", "").strip()
                continue

            # Heure ("→ Samedi 14 mars / 20h30")
            if "→" in content:
                cleaned = content.replace("→", "").strip()
                time_info = cleaned
                continue

            # Description brute, on filtre :
            if (
                len(content) > 8
                and event_title.lower() not in content.lower()
                and "BILLETTERIE" not in content.upper()
                and not content.upper().startswith(("AGENDA", "TÉLÉCHARGEZ"))
                and not content.upper().startswith(("LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE"))
            ):
                description_parts.append(content)

        # Description nette
        description = "\n".join(description_parts).strip()

        # Nettoyage des affreux "1\ner"
        description = description.replace("1\ner", "1er")

        # Récupération heure depuis time_info
        extracted_time = None
        if time_info:
            m = re.search(r"(\d{1,2}h\d{2})", time_info)
            if m:
                extracted_time = m.group(1)

        # Date ISO
        iso_date = convert_to_iso(current_date, extracted_time)

        # Billetterie
        button = section.find("a", class_="elementor-button")
        booking_url = button["href"] if button else None

        events.append({
            "cinema": "Maison des 3 Quartiers",
            "etablissement": "Maison des 3 Quartiers",
            "date_text": current_date,
            "date": iso_date,                # 🔥 ISO
            "title": event_title,
            "subtitle": subtitle,
            "description": description,
            "time": extracted_time,
            "image": image_url,
            "ticket": booking_url,
            "source": URL
        })

    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape_m3q(), indent=2, ensure_ascii=False))
