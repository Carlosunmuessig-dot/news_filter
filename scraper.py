import asyncio
import json
import os
import feedparser
import ssl
import google.generativeai as genai
from playwright.async_api import async_playwright

# SSL-Zertifikatsprüfung für den Mac deaktivieren
ssl._create_default_https_context = ssl._create_unverified_context

# 1. DEIN API KEY
genai.configure(api_key="AQ.Ab8RN6LsIROlz2BHliHLO4KJTtygS644x6Z-y38lAygHO-avyQ")

# 2. DER SYSTEM-PROMPT
SYSTEM_PROMPT = """
Du bist ein hochpräziser Nachrichten-Redakteur. Deine Aufgabe ist es, bereitgestellte Artikeltexte von Qualitätsmedien zu verarbeiten.
DEINE ZIELE:
1. Komprimierung: Fasse jeden übergebenen Artikel auf 20 bis 30 Prozent seiner Originallänge zusammen. Behalte alle wichtigen Fakten bei.
2. Einzel-Artikel: Vermische die Artikel nicht. Jeder Artikel bleibt ein eigener, geschlossener Text.
3. Sprache: Deutsch, sachlich.

KATEGORIEN & SUB-SEKTOREN (Ordne jeden Artikel exakt so ein):
- Wirtschaft (Aktien & Börse, Makroökonomie & Zinsen, Unternehmen & Strategien)
- Politik (Innenpolitik, Außenpolitik, Wahlen & Parteien, Geopolitik, Politik in Amerika)
- Weltweite Schlagzeilen (Breaking News, Globale Ereignisse)
- Lokales & Regionales (Kommunalpolitik, Regionale Wirtschaft, Infrastruktur)
- Kultur & Gesellschaft (Gesellschaftliche Debatten, Kunst & Unterhaltung, Leben & Alltag)
- Sport (Fußball, US-Sport, Olympische Sportarten & Sonstiges)
- Technologie & Wissenschaft (Künstliche Intelligenz & Software, Hardware & Gadgets, Medizin & Forschung, Klima & Umwelt)

AUSGABEFORMAT: Du antwortest AUSSCHLIESSLICH im JSON-Format.
Struktur: {"nachrichten": [{"hauptkategorie": "...", "sub_sektor": "...", "titel": "...", "text": "...", "quelle": "..."}]}
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
   "WiWo": "https://www.wiwo.de/contentexport/feed/rss/schlagzeilen"
}

def clean_cookies(cookies):
    for cookie in cookies:
        if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
            del cookie['sameSite']
    return cookies

async def scrape_and_summarize():
    urls_zum_lesen = []
    
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
        # Tarnung aktivieren
        context = await browser.new_context(
            java_script_enabled=True,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # SCHRITT 1: Links sammeln (jetzt sicher mit Playwright)
        print("Scanne RSS-Feeds nach den jeweils 5 neuesten Artikeln...")
        for name, feed_url in RSS_FEEDS.items():
            try:
                # context.request.get umgeht den Bot-Schutz von Finanzen.net
                response = await context.request.get(feed_url, timeout=15000)
                xml_data = await response.text()
                feed = feedparser.parse(xml_data)
                
                if feed.entries:
                    for entry in feed.entries[:5]:
                        urls_zum_lesen.append(entry.link)
                    print(f"-> {min(5, len(feed.entries))} Links gefunden bei {name}")
                else:
                    print(f"-> Keine Artikel im Feed gefunden ({name})")
            except Exception as e:
                print(f"Fehler beim Lesen des Feeds von {name} (wird übersprungen)")

        if not urls_zum_lesen:
            print("Keine Links in den Feeds gefunden. Abbruch für diesen Durchlauf.")
            await browser.close()
            return

        # SCHRITT 2: Artikelinhalte lesen
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
                text = await page.evaluate("document.body.innerText")
                alle_texte += f"QUELLE: {url}\n\nTEXT:\n{text}\n\n---\n"
            except Exception:
                pass # Fehlerhafte Links leise überspringen
                
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
        with open("nachrichten.json", "w", encoding="utf-8") as f:
            json.dump(neue_daten, f, ensure_ascii=False, indent=2)
        print("Erfolg! Das Dashboard wurde mit den neuesten Nachrichten aktualisiert!")
    except Exception as e:
        print("Fehler beim Verarbeiten durch Gemini:", e)

# ABSTURZSICHERE ENDLOSSCHLEIFE
async def main_loop():
    while True:
        await scrape_and_summarize()
        print("\n[Timer] Warte exakt 17 Minuten (1020 Sekunden) bis zum naechsten Durchlauf...")
        await asyncio.sleep(1020)

if __name__ == "__main__":
    asyncio.run(main_loop())