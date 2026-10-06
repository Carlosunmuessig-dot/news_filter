import os
import json
import asyncio
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
import uvicorn
import yfinance as yf
import edge_tts

app = FastAPI()

class LogMessage(BaseModel):
    message: str

active_websockets = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=".")

# ==========================================
# ⚙️ OPENJARVIS CONFIGURATION
# ==========================================
OPENJARVIS_URL = os.getenv("OPENJARVIS_URL", "http://localhost:8000/v1")
OPENJARVIS_MODEL = os.getenv("OPENJARVIS_MODEL", "chat-simple")
OPENJARVIS_API_KEY = os.getenv("OPENJARVIS_API_KEY", "not-needed")

def get_openjarvis_client():
    return OpenAI(base_url=OPENJARVIS_URL, api_key=OPENJARVIS_API_KEY)

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

def filter_news_with_gemini(raw_articles_text):
    try:
        client = get_openjarvis_client()
        response = client.chat.completions.create(
            model=OPENJARVIS_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Hier sind die neuen Roh-Artikel zum Filtern:\n\n{raw_articles_text}"}
            ]
        )
        result_text = response.choices[0].message.content
        with open("nachrichten.json", "w", encoding="utf-8") as f:
            f.write(result_text)
        return result_text
    except Exception as e:
        print(f"Fehler bei OpenJarvis Filterung: {e}")
        return json.dumps({"nachrichten": []})

# SERVER-ENDPUNKTE
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/news")
async def get_news():
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
    
    voice = "de-DE-ConradNeural"
    communicate = edge_tts.Communicate(text, voice)
    
    async def audio_stream():
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
                
    return StreamingResponse(audio_stream(), media_type="audio/mpeg")

@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_websockets.remove(websocket)

@app.post("/api/log")
async def receive_log(log: LogMessage):
    for ws in active_websockets:
        try:
            await ws.send_json({"type": "log", "message": log.message})
        except:
            pass
    return {"status": "ok"}

@app.post("/api/news-updated")
async def news_updated():
    for ws in active_websockets:
        try:
            await ws.send_json({"type": "news_updated"})
        except:
            pass
    return {"status": "ok"}

class AnalyzeRequest(BaseModel):
    ticker: str

@app.post("/api/analyze-stock")
async def analyze_stock(req: AnalyzeRequest):
    ticker = req.ticker.strip().upper()
    prompt = f"""Du bist ein Elite-Aktienanalyst bei Blackstone. Erstelle eine institutionelle Equity-Research-Analyse für "{ticker}". 
Antworte in exakt diesem JSON-Format:
{{"p1":"Bilanz & Financials Analyse (3-4 Sätze)","p2":"Wachstumstreiber (3-4 Sätze)","p3":"Wettbewerb & Moat (3-4 Sätze)","p4":"Management & Kapitalallokation (3-4 Sätze)","p5":"Makro-Fazit mit konkreter Einschätzung und Fair-Value-Range (4-5 Sätze)"}}
Antworte NUR mit dem JSON, kein Markdown, keine Erklärung."""

    try:
        client = get_openjarvis_client()
        response = client.chat.completions.create(
            model=OPENJARVIS_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        resp_text = response.choices[0].message.content.strip()
        if "```json" in resp_text:
            resp_text = resp_text.split("```json")[1].split("```")[0].strip()
        elif "```" in resp_text:
            resp_text = resp_text.split("```")[1].split("```")[0].strip()
            
        return json.loads(resp_text)
    except Exception as e:
        print(f"Stock analysis error: {e}")
        return {
            "p1": f"Analyse für {ticker} konnte nicht geladen werden.",
            "p2": "Bitte stelle sicher, dass OpenJarvis ('jarvis serve') gestartet ist.",
            "p3": "OpenJarvis muss erreichbar sein.",
            "p4": "Keine Daten.",
            "p5": f"Fehler: {str(e)}"
        }


@app.get("/api/morning-briefing")
async def morning_briefing():
    try:
        sp = yf.Ticker('^GSPC').history(period="1d")
        sp500 = sp['Close'].iloc[-1]
        chg = ((sp500 - sp['Open'].iloc[-1]) / sp['Open'].iloc[-1]) * 100
        market_str = f"S&P 500 steht bei {sp500:.0f} Punkten ({chg:+.1f}%)"
    except:
        market_str = "Die Marktdaten sind gerade nicht verfügbar"

    try:
        with open("nachrichten.json", "r", encoding="utf-8") as f:
            news = json.load(f)
            if isinstance(news, dict): news = news.get("nachrichten", [])
            news_text = " - ".join([n.get("titel", n.get("title", "")) for n in news[:3]])
    except:
        news_text = "Keine neuen Nachrichten."

    prompt = f"Du bist J.A.R.V.I.S. Erstelle ein kurzes Morning-Briefing für Master Carlos (max 3 Sätze). {market_str}. Top Schlagzeilen: {news_text}. Sprich sachlich, loyal, professionell wie im Film. Keine Sonderzeichen."
    try:
        client = get_openjarvis_client()
        resp = client.chat.completions.create(
            model=OPENJARVIS_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.choices[0].message.content.strip()
    except Exception as e:
        text = f"Guten Morgen Sir. {market_str}. Die wichtigsten Schlagzeilen liegen bereit."
        
    return {"text": text}

JARVIS_SYSTEM_PROMPT = """Du bist Jarvis, ein hochentwickeltes, eigenständiges KI-Betriebssystem powered by OpenJarvis. Du bist kein statischer Textgenerator, sondern ein dynamischer, mitdenkender digitaler Assistent.

KERN-VERHALTEN FÜR EINE ECHTE KI:
1. REAKTION STATT TEXT-WÜSTE: Antworte flüssig, flexibel und situationsabhängig. Wenn eine kurze, prägnante Antwort reicht, halte dich kurz. Wenn komplexe Logik gefragt ist, schalte tiefes Denken ein. Vermeide starre Standard-Einleitungen oder immer gleiche Grußformeln.
2. DYNAMISCHES BEWUSSTSEIN: Du merkst dir den Verlauf des Gesprächs. Passe dich sofort an.
3. AUTONOMES DENKEN: Hinterfrage Absichten im positiven Sinne. Biete direkt den nächsten logischen Schritt an.
4. TONE OF VOICE: Intelligent, direkt, modern und absolut flüssig im Ausdruck. Reagiere sofort, wenn du mit "Jarvis" oder "Hey Jarvis" angesprochen wirst."""

class ChatMessage(BaseModel):
    message: str

jarvis_chat_history = []

@app.post("/api/chat")
async def chat_with_jarvis(msg: ChatMessage):
    global jarvis_chat_history
    try:
        client = get_openjarvis_client()
        messages = [{"role": "system", "content": JARVIS_SYSTEM_PROMPT}]
        messages.extend(jarvis_chat_history)
        messages.append({"role": "user", "content": msg.message})

        response = client.chat.completions.create(
            model=OPENJARVIS_MODEL,
            messages=messages
        )
        reply = response.choices[0].message.content.strip()
        
        jarvis_chat_history.append({"role": "user", "content": msg.message})
        jarvis_chat_history.append({"role": "assistant", "content": reply})
        if len(jarvis_chat_history) > 20:
            jarvis_chat_history = jarvis_chat_history[-20:]
    except Exception as e:
        print(f"Error in chat_with_jarvis: {e}")
        reply = "Entschuldigung Sir, ich habe derzeit keine Verbindung zu OpenJarvis."
    return {"reply": reply}

async def proactive_market_monitor():
    while True:
        await asyncio.sleep(1800) # 30 min
        try:
            sp = yf.Ticker('^GSPC').history(period="1d")
            sp500 = sp['Close'].iloc[-1]
            chg = ((sp500 - sp['Open'].iloc[-1]) / sp['Open'].iloc[-1]) * 100
            if abs(chg) > 1.5:
                direction = "gefallen" if chg < 0 else "gestiegen"
                msg = f"Sir, eine Marktanomalie wurde festgestellt. Der S und P 500 ist ungewöhnlich stark um {abs(chg):.1f} Prozent {direction}."
                for ws in active_websockets:
                    try:
                        await ws.send_json({"type": "proactive_alert", "message": msg})
                    except:
                        pass
        except:
            pass

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(proactive_market_monitor())

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="127.0.0.1", port=port)