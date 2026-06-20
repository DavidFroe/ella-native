#!/usr/bin/env python3
"""ella-gemma-assist.py — Gemma-3 als Hilfsmodell fuer die Crash-Recovery.

Eigenstaendig (kein Import von ella-web.py), damit es auch funktioniert,
wenn die Web-Oberflaeche gerade nicht laeuft. Spricht direkt mit owltrail
(lokaler OpenAI-kompatibler Proxy), genau wie ella-web.py es tut.

Aufrufe:
  ella-gemma-assist.py analyze-crash <session_tail_file>
      Liest den letzten Teil einer (zu gross gewordenen) Session und liefert
      einen Fortsetzungs-Prompt auf stdout, mit dem der Bot an exakt der
      Stelle weiterarbeiten kann, an der der Kontext-Fehler auftrat.

  ella-gemma-assist.py judge-done <task_text> <reply_tail_file>
      Vergleicht die urspruengliche Aufgabenbeschreibung mit den juengsten
      Antworten des Bots in der (fortgesetzten) Session. Gibt "DONE" oder
      "NOT_DONE" auf stdout aus (erste Zeile, Rest darf Begruendung sein).
"""
import json
import os
import sys
import urllib.error
import urllib.request

BOT_USER_HOME = os.environ.get("BOT_USER_HOME", os.path.expanduser("~"))
GEMMA3_CONFIG_FILE = os.path.join(BOT_USER_HOME, ".ella_gemma3.json")
OWLTRAIL_PID = os.path.join(BOT_USER_HOME, ".ella_owltrail.pid")


def owltrail_port():
    try:
        with open(OWLTRAIL_PID, encoding="utf-8") as f:
            return int(f.read().splitlines()[1])
    except Exception:
        return 8081


def read_gemma3_config():
    defaults = {"model_id": "124", "context_cap_tokens": 32000}
    try:
        with open(GEMMA3_CONFIG_FILE, encoding="utf-8") as f:
            defaults.update(json.load(f))
    except Exception:
        pass
    return defaults


def ask_gemma(system_content, user_content, max_chars):
    cfg = read_gemma3_config()
    if len(user_content) > max_chars:
        user_content = "[...gekuerzt...]\n" + user_content[-max_chars:]
    body = json.dumps({
        "model": cfg["model_id"],
        "stream": False,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
    }).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{owltrail_port()}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer ella"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=120)
    data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


def analyze_crash(tail_text):
    cfg = read_gemma3_config()
    cap_chars = int(cfg["context_cap_tokens"]) * 3  # Sicherheitsabstand, grobe Heuristik
    system_content = (
        "Du bekommst das Ende eines Chat-Verlaufs, in dem ein KI-Assistent (Klauski) "
        "mit einem Nutzer gearbeitet hat. Der Verlauf ist zu gross fuer das Modell geworden "
        "und die Konversation ist deswegen hart abgebrochen (Kontext-Fehler), OHNE dass "
        "die Aufgabe fertig wurde. Deine Aufgabe: Lies den Verlauf und schreibe einen kurzen, "
        "klaren Fortsetzungs-Prompt, mit dem Klauski GENAU an der Stelle weiterarbeiten kann, "
        "an der es abgerissen ist. Nenne konkret: worum es geht, was schon erledigt ist, was "
        "noch fehlt. Schreib NUR den Fortsetzungs-Prompt selbst (als Anweisung an Klauski, "
        "du-Form), keine Meta-Kommentare, keine Ueberschriften, kein Praeamble."
    )
    return ask_gemma(system_content, tail_text, cap_chars)


def judge_done(task_text, reply_tail):
    cfg = read_gemma3_config()
    cap_chars = int(cfg["context_cap_tokens"]) * 3
    system_content = (
        "Du bewertest, ob eine an einen KI-Assistenten gestellte Aufgabe inzwischen erledigt "
        "ist. Du bekommst die Aufgabenbeschreibung und die juengsten Nachrichten aus dem Chat. "
        "Antworte auf der ERSTEN Zeile NUR mit dem Wort DONE oder NOT_DONE (nichts anderes auf "
        "dieser Zeile). Danach darfst du in 1 Satz begruenden."
    )
    user_content = f"AUFGABE:\n{task_text}\n\nJUENGSTE NACHRICHTEN:\n{reply_tail}"
    if len(user_content) > cap_chars:
        user_content = user_content[-cap_chars:]
    return ask_gemma(system_content, user_content, cap_chars)


def main():
    if len(sys.argv) < 2:
        print("Usage: ella-gemma-assist.py <analyze-crash|judge-done> ...", file=sys.stderr)
        sys.exit(1)
    mode = sys.argv[1]
    try:
        if mode == "analyze-crash":
            tail_file = sys.argv[2]
            with open(tail_file, encoding="utf-8") as f:
                tail_text = f.read()
            print(analyze_crash(tail_text))
        elif mode == "judge-done":
            task_text = sys.argv[2]
            reply_file = sys.argv[3]
            with open(reply_file, encoding="utf-8") as f:
                reply_tail = f.read()
            print(judge_done(task_text, reply_tail))
        else:
            print(f"Unbekannter Modus: {mode}", file=sys.stderr)
            sys.exit(1)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, KeyError, json.JSONDecodeError) as e:
        print(f"GEMMA_ERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
