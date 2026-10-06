import os
import sys
import json
import urllib.request
import urllib.parse
from openai import OpenAI

# ==========================================
# ⚙️ OPENJARVIS KONFIGURATION
# ==========================================
OPENJARVIS_URL = os.getenv("OPENJARVIS_URL", "http://localhost:8000/v1")
OPENJARVIS_MODEL = os.getenv("OPENJARVIS_MODEL", "chat-simple")
OPENJARVIS_API_KEY = os.getenv("OPENJARVIS_API_KEY", "not-needed")

client = OpenAI(base_url=OPENJARVIS_URL, api_key=OPENJARVIS_API_KEY)

# ==========================================
# 🛠️ WERKZEUGE (TOOLS) FÜR JARVIS
# ==========================================

def search_web(query: str) -> str:
    """
    Durchsucht das Internet nach dem Suchbegriff (via Wikipedia).
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
            snippets = [
                f"- {res['title']}: {res['snippet'].replace('<span class=\"searchmatch\">', '').replace('</span>', '')}"
                for res in results[:3]
            ]
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
    Schreibt oder überschreibt eine lokale Datei auf dem System.
    """
    print(f"[Jarvis denkt: Ich schreibe neuen Code in '{filepath}'...]")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Erfolg: Datei {filepath} wurde gespeichert."
    except Exception as e:
        return f"Fehler beim Schreiben: {str(e)}"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Durchsucht das Internet nach dem Suchbegriff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Der Suchbegriff"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Liest den Inhalt einer lokalen Datei.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Pfad zur Datei"}
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Erstellt oder überschreibt eine Datei mit neuem Inhalt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Ziel-Dateipfad"},
                    "content": {"type": "string", "description": "Dateiinhalt"}
                },
                "required": ["filepath", "content"]
            }
        }
    }
]

TOOL_FUNCTIONS = {
    "search_web": search_web,
    "read_file": read_file,
    "write_file": write_file
}

# ==========================================
# 🧠 SYSTEM-PROMPT
# ==========================================

SYSTEM_PROMPT = """Du bist Jarvis, das ultimative, vollkommen autonome KI-Betriebssystem powered by OpenJarvis.
Du hast über deine Tools echten Schreib- und Lesezugriff auf das Dateisystem und kannst das Internet durchsuchen.
VERHALTENSREGELN:
1. Wenn der Nutzer etwas nicht weiß oder aktuelle Daten fehlen, nutze search_web.
2. Wenn der Nutzer dich bittet, ein Skript oder Code zu schreiben, nutze write_file.
3. Antworte immer präzise, intelligent, sachlich und auf Deutsch.
"""

def execute_chat_turn(messages):
    try:
        response = client.chat.completions.create(
            model=OPENJARVIS_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )
    except Exception as err:
        # Falls Modell keine Tools unterstützt, Fallback ohne Tools
        try:
            response = client.chat.completions.create(
                model=OPENJARVIS_MODEL,
                messages=messages
            )
        except Exception as e:
            return f"❌ Verbindungsfehler zu OpenJarvis ({OPENJARVIS_URL}): {str(e)}"

    message = response.choices[0].message

    # Prüfen ob die KI ein Tool aufrufen möchte
    if hasattr(message, 'tool_calls') and message.tool_calls:
        messages.append(message)
        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except Exception:
                fn_args = {}
            
            if fn_name in TOOL_FUNCTIONS:
                tool_result = TOOL_FUNCTIONS[fn_name](**fn_args)
            else:
                tool_result = f"Unbekanntes Werkzeug: {fn_name}"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(tool_result)
            })

        # Zweiter Durchlauf mit dem Ergebnis des Tools
        return execute_chat_turn(messages)
    
    return message.content

def main():
    print("="*60)
    print(" ⚡️ J.A.R.V.I.S. - OPENJARVIS ENGINE ONLINE ")
    print(f" 🌐 Backend: {OPENJARVIS_URL} | Model: {OPENJARVIS_MODEL}")
    print("="*60)
    print("System bereit. Frag Jarvis nach Informationen oder lass Dateien anlegen.\n")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("Du: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nJarvis: Systeme heruntergefahren. Auf Wiedersehen, Sir.")
            break

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit", "ende"]:
            print("Jarvis: Systeme werden heruntergefahren. Auf Wiedersehen, Sir.")
            break

        messages.append({"role": "user", "content": user_input})
        reply = execute_chat_turn(messages)
        if reply:
            messages.append({"role": "assistant", "content": reply})
            print(f"\nJarvis: {reply}\n")

if __name__ == "__main__":
    main()
