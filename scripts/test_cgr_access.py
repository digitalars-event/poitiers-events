#!/usr/bin/env python3
# coding: utf-8

import requests

CGR_URLS = {
    "CGR Buxerolles": "https://www.cgrcinemas.fr/horaire-film/p0736-cgr-buxerolles-poitiers/",
    "CGR Castille": "https://www.cgrcinemas.fr/horaire-film/p0096-cgr-poitiers-castille/",
    "CGR Fontaine-le-Comte": "https://www.cgrcinemas.fr/horaire-film/w8624-cgr-fontaine-le-comte-poitiers/"
}

def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36"
    }

    for name, url in CGR_URLS.items():
        print(f"\n🎯 Test d'accès : {name}")
        try:
            response = requests.get(url, headers=headers, timeout=15)
            print(f"➡️ Statut HTTP : {response.status_code}")
            print(f"📦 Taille du contenu : {len(response.text)} caractères")

            # Aperçu du début du HTML
            snippet = response.text[:500].replace("\n", " ")
            print(f"🔍 Aperçu HTML : {snippet[:200]}...")

        except Exception as e:
            print(f"❌ Erreur lors de l'accès à {name} : {e}")

if __name__ == "__main__":
    main()
