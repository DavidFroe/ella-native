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
import time
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


def ask_gemma(system_content, user_content, max_chars, model_id=None, retries=2):
    # Das Backend antwortet vereinzelt mit Status 200 aber leerem Body (kein
    # Logikfehler hier, beobachtete Flakiness) -- kurzer Retry statt sofort
    # aufzugeben.
    cfg = read_gemma3_config()
    if len(user_content) > max_chars:
        user_content = "[...gekuerzt...]\n" + user_content[-max_chars:]
    body = json.dumps({
        "model": model_id or cfg["model_id"],
        "stream": False,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
    }).encode()
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{owltrail_port()}/v1/chat/completions",
                data=body,
                headers={"Content-Type": "application/json", "Authorization": "Bearer ella"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=120)
            raw = resp.read()
            if not raw.strip():
                raise json.JSONDecodeError("empty response body", "", 0)
            data = json.loads(raw)
            return data["choices"][0]["message"]["content"].strip()
        except (json.JSONDecodeError, KeyError, urllib.error.URLError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(2)
                continue
            raise last_err


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
        "noch fehlt. WICHTIG: der alte Chat-Verlauf wird zusammen mit dieser Wiederaufnahme "
        "GELOESCHT (nicht aber Dateien auf der Festplatte) -- Klauski hat danach KEIN eigenes "
        "Gedaechtnis mehr an Details aus dem alten Verlauf. Nenne deshalb UNBEDINGT alle "
        "konkreten Datei-/Ordnerpfade, Dateinamen, IDs oder sonstigen Details, die er braucht, "
        "um mit denselben Dateien/Ressourcen weiterzuarbeiten -- sonst kann er sie nicht "
        "wiederfinden. Schreib NUR den Fortsetzungs-Prompt selbst (als Anweisung an Klauski, "
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


def review_session(transcript_text, model_id=None, context_cap_tokens=None):
    """Lässt das Reviewer-Modell beurteilen, ob eine Session fuer den Nutzer
    zufriedenstellend abgeschlossen aussieht, oder ob der Bot wahrscheinlich
    kein adäquates Ergebnis geliefert hat und nachgehakt werden sollte.

    Antwortformat (erste Zeile): OK  ODER  FOLLOWUP
    Bei FOLLOWUP folgt ab Zeile 2 ein konkreter Fortsetzungs-Prompt fuer den Bot."""
    cap_chars = int(context_cap_tokens or read_gemma3_config()["context_cap_tokens"]) * 3
    system_content = (
        "Du bewertest eine abgeschlossene oder zumindest pausierte Chat-Unterhaltung zwischen "
        "einem KI-Assistenten (Klauski) und einem Nutzer. Du bekommst den (ggf. am Anfang "
        "gekuerzten) Verlauf -- das Ende des Verlaufs ist der aktuellste Stand. "
        "Frage dich: Sieht das fuer den Nutzer nach einem zufriedenstellend abgeschlossenen "
        "Anliegen aus, oder hat der Assistent wahrscheinlich KEIN adäquates Ergebnis fuer das "
        "geliefert, was der Nutzer eigentlich wollte (z.B. abgebrochen, ausgewichen, "
        "offensichtlich falsch verstanden, eine Zwischenfrage nie beantwortet)? "
        "Sei zurueckhaltend mit FOLLOWUP -- nur bei klaren Anzeichen, nicht bei jeder kurzen "
        "oder informellen Unterhaltung. "
        "Antworte auf der ERSTEN Zeile NUR mit dem Wort OK oder FOLLOWUP (nichts anderes auf "
        "dieser Zeile). Bei FOLLOWUP schreib AB DER ZWEITEN ZEILE einen kurzen, konkreten "
        "Fortsetzungs-Prompt fuer Klauski (du-Form), der beschreibt was fehlt/offen blieb "
        "und was er als naechstes tun soll, um es nachzuholen."
    )
    return ask_gemma(system_content, transcript_text, cap_chars, model_id=model_id)


def main():
    if len(sys.argv) < 2:
        print("Usage: ella-gemma-assist.py <analyze-crash|judge-done|review-session> ...", file=sys.stderr)
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
        elif mode == "review-session":
            transcript_file = sys.argv[2]
            model_id = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
            context_cap = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else None
            with open(transcript_file, encoding="utf-8") as f:
                transcript_text = f.read()
            print(review_session(transcript_text, model_id=model_id, context_cap_tokens=context_cap))
        else:
            print(f"Unbekannter Modus: {mode}", file=sys.stderr)
            sys.exit(1)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, KeyError, json.JSONDecodeError) as e:
        print(f"GEMMA_ERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
