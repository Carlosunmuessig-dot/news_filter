import os
import json
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.generativeai as genai
import uvicorn
import yfinance as yf
import edge_tts

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=".")

# 1. GEMINI CONFIG (Ersetze 'DEIN_API_KEY' mit deinem echten Key)
genai.configure(api_key=os.environ.get("AQ.Ab8RN6LsIROlz2BHliHLO4KJTtygS644x6Z-y38lAygHO-avyQ"))

SYSTEM_PROMPT = """
Du bist ein hochpräziser Nachrichten-Redakteur. Deine Aufgabe ist es, bereitgestellte Artikeltexte von Qualitätsmedien zu verarbeiten.
DEINE ZIELE:
1. Komprimierung: Fasse jeden übergebenen Artikel auf 20 bis 30 Prozent seiner Originallänge zusammen. Behalte alle wichtigen Fakten bei.
2. Einzel-Artikel: Vermische die Artikel nicht. Jeder Artikel bleibt ein eigener, geschlossener Text.
3. Sprache: Deutsch, sachlich.
KATEGORIEN & SUB-SEKTOREN:
- Wirtschaft (Unternehmen & Märkte, Makroökonomie & Zinsen, Internationale Handelsbeziehungen)
- Lokales & Regionales (Kommunalpolitik, Regionale Wirtschaft, Infrastruktur)
- Kultur & Gesellschaft (Gesellschaftliche Debatten, Kunst & Unterhaltung, Leben & Alltag)
- Sport (Fußball, US-Sport, Olympische Sportarten & Sonstiges)
- Technologie & Wissenschaft (Künstliche Intelligenz & Software, Hardware & Gadgets, Medizin & Forschung, Klima & Umwelt)

AUSGABEFORMAT: Du antwortest AUSSCHLIESSLICH im JSON-Format. Keine Markdown-Blöcke (kein ```json). Deine Antwort muss direkt als JSON geparst werden können.
Struktur: {"nachrichten": [{"hauptkategorie": "...", "sub_sektor": "...", "titel": "...", "text": "...", "quelle": "..."}]}
"""

# 2. FUNKTION: Artikel an Gemini senden und filtern
def filter_news_with_gemini(raw_articles_text):
    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro",
        generation_config={"response_mime_type": "application/json"},
        system_instruction=SYSTEM_PROMPT
    )
    
    response = model.generate_content(f"Hier sind die neuen Roh-Artikel zum Filtern:\n\n{raw_articles_text}")
    
    # Ergebnis lokal speichern
    with open("nachrichten.json", "w", encoding="utf-8") as f:
        f.write(response.text)
    return response.text

# 3. SERVER-ENDPUNKTE
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # Lädt die Website im Browser
    return templates.TemplateResponse(request=request, name="index.html")
@app.get("/api/news")
async def get_news():
    # Liefert die gefilterten Nachrichten an die Website
    try:
        with open("nachrichten.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"nachrichten": []}

@app.get("/api/stocks")
async def get_stocks(tickers: str = ""):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return {"stocks": {}}
    
    results = {}
    for t in ticker_list:
        try:
            info = yf.Ticker(t).fast_info
            last_price = info.last_price
            prev_close = info.previous_close
            change_pct = ((last_price - prev_close) / prev_close) * 100 if prev_close else 0
            results[t] = {
                "price": round(float(last_price), 2),
                "change": round(float(change_pct), 2)
            }
        except Exception:
            pass
    return {"stocks": results}

@app.get("/api/tts")
async def get_tts(text: str = ""):
    if not text:
        return {"error": "No text provided"}
    
    # Der gewählte deutsche Sprecher für Jarvis
    voice = "de-DE-ConradNeural"
    communicate = edge_tts.Communicate(text, voice)
    
    async def audio_stream():
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
                
    return StreamingResponse(audio_stream(), media_type="audio/mpeg")

if __name__ == "__main__":
    # Startet den lokalen Server auf http://localhost:8000
    uvicorn.run(app, host="127.0.0.1", port=8000)