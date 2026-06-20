#!/usr/bin/env python3
"""ella-bigloop.py — rotiert durch OpenClaw-Sessions und laesst ein
Reviewer-Modell (Standard: Gemma) beurteilen, ob eine Unterhaltung fuer
den Nutzer zufriedenstellend abgeschlossen aussieht.

Laeuft NUR, wenn keine "Grosse Aufgabe" aktiv ist (die Bigloop sucht sich
quasi selbst Arbeit, wenn der Bot sonst nichts zu tun hat) und nur, wenn
das eigene Intervall seit dem letzten Lauf abgelaufen ist.

Aufruf: ella-bigloop.py check
Gibt bei einem Verdachtsfall eine Zeile aus:
  FOLLOWUP\t<session_key>\t<prompt_tempfile>\t<kurzes_label>
Sonst keine Ausgabe (auch wenn regulaer reviewed wurde -- nur Logging
intern via stderr, die eigentliche Aktion entscheidet ella-bigloop/bash).
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
BOT_USER_HOME = os.environ.get("BOT_USER_HOME", os.path.expanduser("~"))
CONFIG_FILE = os.path.join(BOT_USER_HOME, ".ella_bigloop.json")
TASK_FILE = os.path.join(BOT_USER_HOME, ".ella_task.json")
SESSIONS_DIR = os.path.join(BOT_USER_HOME, ".openclaw", "agents", "main", "sessions")
GEMMA_ASSIST_PY = os.path.join(BASE_DIR, "ella-gemma-assist.py")

DEFAULTS = {
    "enabled": False,
    "interval_seconds": 900,
    "model_id": "124",
    "context_cap_tokens": 32000,
    "rotation_index": 0,
    "last_run_at": None,
}

# Synthetische Sessions, die kein echtes Nutzergespraech sind.
SKIP_KEYS = {"agent:main:watchdog-ping"}


def load_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULTS)


def save_config(cfg):
    d = os.path.dirname(CONFIG_FILE) or "."
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_FILE)


def now():
    return datetime.datetime.now().astimezone()


def task_is_active():
    try:
        with open(TASK_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("status") == "in_progress"
    except Exception:
        return False


def list_session_keys():
    try:
        with open(os.path.join(SESSIONS_DIR, "sessions.json"), encoding="utf-8") as f:
            store = json.load(f)
    except Exception:
        return []
    return sorted(k for k in store.keys() if k not in SKIP_KEYS)


def session_id_for(key):
    try:
        with open(os.path.join(SESSIONS_DIR, "sessions.json"), encoding="utf-8") as f:
            store = json.load(f)
        return store.get(key, {}).get("sessionId")
    except Exception:
        return None


def read_session_text(session_id, max_bytes=150_000):
    path = os.path.join(SESSIONS_DIR, session_id + ".jsonl")
    try:
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            return f.read()
    except Exception:
        return None


def review_with_gemma(text, model_id, context_cap_tokens):
    fd, tmp = tempfile.mkstemp(dir=BOT_USER_HOME, prefix=".ella_bigloop_tail_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        proc = subprocess.run(
            ["python3", GEMMA_ASSIST_PY, "review-session", tmp, model_id or "", str(context_cap_tokens or "")],
            capture_output=True, text=True, timeout=90,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()
    except Exception:
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _dbg(debug, msg):
    if debug:
        print(f"[bigloop-debug] {msg}", file=sys.stderr)


def main():
    force = "--force" in sys.argv[1:]
    debug = "--debug" in sys.argv[1:] or force
    cfg = load_config()
    _dbg(debug, f"config: enabled={cfg.get('enabled')} interval={cfg.get('interval_seconds')}s "
                f"model={cfg.get('model_id')} context_cap={cfg.get('context_cap_tokens')} "
                f"rotation_index={cfg.get('rotation_index')} last_run_at={cfg.get('last_run_at')}")

    if not cfg.get("enabled") and not force:
        _dbg(debug, "EXIT: bigloop ist deaktiviert (ella bigloop on)")
        return

    last_run = cfg.get("last_run_at")
    if last_run and not force:
        try:
            elapsed = (now() - datetime.datetime.fromisoformat(last_run)).total_seconds()
            if elapsed < cfg.get("interval_seconds", 900):
                _dbg(debug, f"EXIT: Intervall noch nicht abgelaufen ({elapsed:.0f}s von {cfg.get('interval_seconds', 900)}s)")
                return
        except Exception:
            pass

    if task_is_active():
        _dbg(debug, "EXIT: eine 'Grosse Aufgabe' ist gerade aktiv -- Bigloop bleibt dormant")
        return

    keys = list_session_keys()
    _dbg(debug, f"{len(keys)} Session(s) gefunden: {keys}")
    if not keys:
        _dbg(debug, "EXIT: keine Sessions vorhanden")
        return

    idx = cfg.get("rotation_index", 0) % len(keys)
    session_key = keys[idx]
    cfg["rotation_index"] = (idx + 1) % len(keys)
    cfg["last_run_at"] = now().isoformat()
    save_config(cfg)
    _dbg(debug, f"gewaehlt (Rotation-Index {idx}): {session_key}")

    session_id = session_id_for(session_key)
    if not session_id:
        _dbg(debug, "EXIT: keine sessionId fuer diesen Key gefunden")
        return
    text = read_session_text(session_id)
    if not text or not text.strip():
        _dbg(debug, "EXIT: Session-Transkript leer/nicht lesbar")
        return
    _dbg(debug, f"Transkript gelesen: {len(text)} Zeichen (sessionId={session_id})")

    model_id = cfg.get("model_id")
    context_cap = cfg.get("context_cap_tokens")
    _dbg(debug, f"sende an Reviewer-Modell '{model_id}' (Kontext-Cap {context_cap} Tok. ~{int(context_cap)*3} Zeichen)")
    verdict = review_with_gemma(text, model_id, context_cap)
    if not verdict:
        _dbg(debug, "EXIT: Reviewer-Modell hat nicht/leer geantwortet")
        return
    _dbg(debug, f"Antwort vom Reviewer-Modell:\n{'-'*40}\n{verdict}\n{'-'*40}")

    lines = verdict.splitlines()
    first = (lines[0].strip().upper() if lines else "")
    if first != "FOLLOWUP":
        _dbg(debug, f"ERGEBNIS: '{first}' -> kein Nachhaken noetig, Session wird so belassen")
        return

    followup_prompt = "\n".join(lines[1:]).strip()
    if not followup_prompt:
        _dbg(debug, "EXIT: FOLLOWUP erkannt, aber kein Prompt-Text dahinter")
        return
    _dbg(debug, f"ERGEBNIS: FOLLOWUP -> setze Aufgabe mit Prompt:\n{followup_prompt}")

    fd, prompt_file = tempfile.mkstemp(dir=BOT_USER_HOME, prefix=".ella_bigloop_prompt_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(followup_prompt)

    label = followup_prompt.splitlines()[0][:120]
    print(f"FOLLOWUP\t{session_key}\t{prompt_file}\t{label}")


if __name__ == "__main__":
    main()
