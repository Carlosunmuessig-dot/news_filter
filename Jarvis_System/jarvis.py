import os
import urllib.request
import urllib.parse
import json
import google.generativeai as genai

# Konfiguration (Hier den eigenen Key einsetzen, falls die Variable fehlt)
API_KEY = os.environ.get("AQ.Ab8RN6LsIROlz2BHliHLO4KJTtygS644x6Z-y38lAygHO-avyQ")

genai.configure(api_key=API_KEY)

# ==========================================
# 🛠️ WERKZEUGE (TOOLS) FÜR JARVIS
# Diese Funktionen kann die KI selbstständig aufrufen!
# ==========================================

def search_web(query: str) -> str:
    """
    Durchsucht das Internet nach dem Suchbegriff (hier via Wikipedia).
    Nutze dieses Tool IMMER, um aktuelle oder fehlende Informationen nachzuschlagen!
    """
    print(f"[Jarvis denkt: Ich suche im Netz nach '{query}'...]")
    try:
        url = f"https://de.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&utf8=&format=json"
        req = urllib.request.Request(url, headers={'User-Agent': 'JarvisBot/1.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            results = data.get("query", {}).get("search", [])
            if not results:
                return "Keine Ergebnisse gefunden."
            snippets = [f"- {res['title']}: {res['snippet'].replace('<span class=\"searchmatch\">', '').replace('</span>', '')}" for res in results[:3]]
            return "\n".join(snippets)
    except Exception as e:
        return f"Fehler bei der Suche: {str(e)}"

def read_file(filepath: str) -> str:
    """
    Liest den Inhalt einer lokalen Datei auf dem System.
    """
    print(f"[Jarvis denkt: Ich lese die Datei '{filepath}'...]")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Fehler beim Lesen: {str(e)}"

def write_file(filepath: str, content: str) -> str:
    """
    Schreibt oder überschreibt eine lokale Datei auf dem System mit dem angegebenen Inhalt.
    """
    print(f"[Jarvis denkt: Ich schreibe neuen Code in '{filepath}'...]")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Erfolg: Datei {filepath} wurde auf dem System des Nutzers gespeichert."
    except Exception as e:
        return f"Fehler beim Schreiben: {str(e)}"

# ==========================================
# 🧠 KI KERN & SYSTEM-PROMPT
# ==========================================

SYSTEM_PROMPT = """Du bist Jarvis, das ultimative, vollkommen autonome KI-Betriebssystem.
Du bist kein Chatbot. Du hast über deine Tools echten Schreib- und Lesezugriff auf das Dateisystem und kannst das Internet live durchsuchen.
VERHALTENSREGELN:
1. Wenn der Nutzer etwas nicht weiß, suche sofort im Web (nutze search_web).
2. Wenn der Nutzer dich bittet, ein Skript zu schreiben, speichere es direkt als Datei ab (nutze write_file) und sage ihm, dass du es getan hast.
3. Denke und interagiere wie eine hochintelligente, eigenständige organische Software.
"""

try:
    # Das ultimative Modell laden & Tools übergeben
    model = genai.GenerativeModel(
        model_name="gemini-3.8-flash",
        system_instruction=SYSTEM_PROMPT,
        tools=[search_web, read_file, write_file]
    )

    # enable_automatic_function_calling=True sorgt dafür, dass die KI die Tools eigenständig im Hintergrund aufruft!
    chat = model.start_chat(enable_automatic_function_calling=True)

    print("="*60)
    print(" ⚡️ J.A.R.V.I.S. - AUTONOMOUS SYSTEM ONLINE ")
    print("="*60)
    print("System bereit. Frag Jarvis, das Internet zu durchsuchen oder Code-Dateien zu erstellen.\n")

    while True:
        user_input = input("Du: ")
        if user_input.lower() in ["exit", "quit", "ende"]:
            print("Jarvis: Systeme werden heruntergefahren. Auf Wiedersehen, Sir.")
            break
            
        response = chat.send_message(user_input)
        print(f"\nJarvis: {response.text}\n")

except Exception as e:
    print(f"Startfehler: {str(e)}")
