import asyncio
import json
import os
import feedparser
import ssl
from bs4 import BeautifulSoup
import google.generativeai as genai
from playwright.async_api import async_playwright

# SSL-Zertifikatsprüfung deaktivieren
ssl._create_default_https_context = ssl._create_unverified_context

# 1. DEIN API KEY
genai.configure(api_key="AQ.Ab8RN6LsIROlz2BHliHLO4KJTtygS644x6Z-y38lAygHO-avyQ")

# 2. DER SYSTEM-PROMPT
SYSTEM_PROMPT = """
Du bist ein hochpräziser Nachrichten-Redakteur. Deine Aufgabe ist es, bereitgestellte Artikeltexte von Qualitätsmedien zu verarbeiten.
DEINE ZIELE:
1. Komprimierung: Fasse jeden Artikel verständlich in 3 bis 4 Sätzen zusammen. Die wichtigsten Punkte und Zusammenhänge müssen sofort klar werden.
2. Einzel-Artikel: Vermische die Artikel nicht. Jeder Artikel bleibt ein eigener, geschlossener Text.
3. Fokus: Achte besonders darauf, Artikel über Künstliche Intelligenz, Robotik, Software und globale Tech-Entwicklungen sowie Börsen- und Wirtschaftstrends detailliert und präzise aufzubereiten.
4. Sprache: Deutsch, sachlich und wahrheitsgetreu.

KATEGORIEN & SUB-SEKTOREN (Ordne jeden Artikel exakt so ein):
- Wirtschaft (Aktien & Börse, Makroökonomie & Zinsen, Unternehmen & Strategien)
- Politik (Innenpolitik, Außenpolitik, Wahlen & Parteien, Geopolitik, Politik in Amerika)
- Weltweite Schlagzeilen (Breaking News, Globale Ereignisse)
- Lokales & Regionales (Kommunalpolitik, Regionale Wirtschaft, Infrastruktur)
- Kultur & Gesellschaft (Gesellschaftliche Debatten, Kunst & Unterhaltung, Leben & Alltag)
- Sport (Fußball, US-Sport, Olympische Sportarten & Sonstiges)
- Technologie & Wissenschaft (Künstliche Intelligenz & Software, Hardware & Robotik, Medizin & Forschung, Klima & Umwelt)

AUSGABEFORMAT: Du antwortest AUSSCHLIESSLICH im JSON-Format.
Struktur: {"nachrichten": [{"hauptkategorie": "...", "sub_sektor": "...", "titel": "...", "text": "...", "quelle": "..."}]}
WICHTIG: Setze bei "quelle" den originalen Link zum Artikel ein.
"""

# 3. RSS-FEEDS
RSS_FEEDS = {
    "Handelsblatt": "https://www.handelsblatt.com/contentexport/feed/wirtschaft",
    "Zeit": "https://newsfeed.zeit.de/index",
    "Tagesschau": "https://www.tagesschau.de/infoservices/alle-meldungen-100~rdf.xml",
    "n-tv": "https://www.n-tv.de/wirtschaft/rss",
    "Spiegel": "https://www.spiegel.de/index.rss",
    "Welt": "https://www.welt.de/feeds/latest.rss",
    "WSJ": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "Washington Post": "https://feeds.washingtonpost.com/rss/world",
    "WiWo": "https://www.wiwo.de/contentexport/feed/rss/schlagzeilen",
    "Heise": "https://www.heise.de/rss/heise-atom.xml",
    "Golem": "https://rss.golem.de/rss.php?feed=RSS2.0",
    "t3n": "https://t3n.de/rss.xml",
    "Manager Magazin": "https://www.manager-magazin.de/index.rss"
}

def clean_cookies(cookies):
    for cookie in cookies:
        if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
            del cookie['sameSite']
    return cookies

async def scrape_and_summarize():
    urls_zum_lesen = []
    bild_mapping = {} 
    
    cookies_handelsblatt = []
    cookies_zeit = []
    if os.path.exists("cookies_handelsblatt.json"):
        with open("cookies_handelsblatt.json", "r") as f:
            cookies_handelsblatt = clean_cookies(json.load(f))
    if os.path.exists("cookies_zeit.json"):
        with open("cookies_zeit.json", "r") as f:
            cookies_zeit = clean_cookies(json.load(f))

    print("\nStarte den getarnten Browser für Feeds und Artikel...")
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context(
            java_script_enabled=True,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # SCHRITT 1: Links sammeln UND Bilder direkt aus dem Feed sichern (Anti-Blocker)
        print("Scanne RSS-Feeds nach den neuesten Artikeln...")
        for name, feed_url in RSS_FEEDS.items():
            try:
                response = await context.request.get(feed_url, timeout=15000)
                xml_data = await response.text()
                feed = feedparser.parse(xml_data)
                
                if feed.entries:
                    for entry in feed.entries[:10]:
                        if entry.link not in urls_zum_lesen:
                            urls_zum_lesen.append(entry.link)
                            
                            # Bild-Link aus dem Feed extrahieren
                            bild_url = ""
                            if 'media_content' in entry and len(entry.media_content) > 0:
                                bild_url = entry.media_content[0].get('url', '')
                            elif 'links' in entry:
                                for link in entry.links:
                                    if 'image' in link.get('type', ''):
                                        bild_url = link.get('href', '')
                            elif 'enclosures' in entry and len(entry.enclosures) > 0:
                                bild_url = entry.enclosures[0].get('href', '')
                            
                            bild_mapping[entry.link] = bild_url

                    print(f"-> Links gefunden bei {name}")
                else:
                    print(f"-> Keine Artikel im Feed gefunden ({name})")
            except Exception as e:
                print(f"Fehler beim Lesen des Feeds von {name}")

        if not urls_zum_lesen:
            print("Keine Links in den Feeds gefunden. Abbruch.")
            await browser.close()
            return

        # SCHRITT 2: Artikelinhalte lesen (und falls Feed kein Bild hatte, Webseite als Backup scannen)
        print(f"\nLese jetzt {len(urls_zum_lesen)} Artikel aus...")
        alle_texte = ""
        for url in urls_zum_lesen:
            try:
                await context.clear_cookies()
                if "handelsblatt.com" in url and cookies_handelsblatt:
                    await context.add_cookies(cookies_handelsblatt)
                elif "zeit.de" in url and cookies_zeit:
                    await context.add_cookies(cookies_zeit)
                
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Wenn im Feed kein Bild war, versuchen wir es als Backup über die Website
                if not bild_mapping.get(url):
                    html_code = await page.content()
                    soup = BeautifulSoup(html_code, 'html.parser')
                    image_tag = soup.find("meta", property="og:image")
                    if image_tag and image_tag.get("content"):
                        bild_mapping[url] = image_tag["content"]

                text = await page.evaluate("document.body.innerText")
                alle_texte += f"QUELLE: {url}\n\nTEXT:\n{text[:5000]}\n\n---\n"
            except Exception:
                pass 
                
        await browser.close()

    if not alle_texte.strip():
        print("Keine Texte extrahiert. Abbruch.")
        return

    print("Sende geballte Artikel an Gemini zur Analyse...")
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config={"response_mime_type": "application/json"},
        system_instruction=SYSTEM_PROMPT
    )
    
    try:
        response = await model.generate_content_async(alle_texte)
        neue_daten = json.loads(response.text)
        neue_artikel = neue_daten.get("nachrichten", [])
        
        # BILDER ZUWEISEN
        for artikel in neue_artikel:
            art_link = artikel.get("quelle", "")
            artikel["bild"] = bild_mapping.get(art_link, "")

        # HISTORIE LADEN
        bestehende_nachrichten = []
        if os.path.exists("nachrichten.json"):
            with open("nachrichten.json", "r", encoding="utf-8") as f:
                try:
                    bestehende = json.load(f)
                    if isinstance(bestehende, list):
                        bestehende_nachrichten = bestehende
                except:
                    pass

        # Doppelte vermeiden & neue vorne einfügen
        bekannte_titel = {item.get("titel", "") for item in bestehende_nachrichten}
        for artikel in neue_artikel:
            if artikel.get("titel") and artikel.get("titel") not in bekannte_titel:
                bestehende_nachrichten.insert(0, artikel)

        # Abspeichern
        with open("nachrichten.json", "w", encoding="utf-8") as f:
            json.dump(bestehende_nachrichten, f, ensure_ascii=False, indent=2)
            
        print(f"Erfolg! Archiv enthält jetzt {len(bestehende_nachrichten)} Artikel mit Bildern.")
    except Exception as e:
        print("Fehler beim Verarbeiten durch Gemini:", e)

async def main_loop():
    while True:
        await scrape_and_summarize()
        print("\n[Timer] Warte 17 Minuten bis zum naechsten Durchlauf...")
        await asyncio.sleep(1020)

if __name__ == "__main__":
    asyncio.run(main_loop())