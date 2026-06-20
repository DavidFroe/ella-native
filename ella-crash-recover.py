#!/usr/bin/env python3
"""ella-crash-recover.py — erkennt Sessions, die im Gateway an einem
Kontext-Ueberlauf ("Context is too large...") haengen geblieben sind, und
bereitet die automatische Wiederaufnahme vor.

Wird von ella-watchdog bei jedem Check aufgerufen (read-only Analyse-Teil).
Die eigentlichen Aktionen (Session leeren, Gateway neu starten, Prompt
reinjizieren, Nutzer benachrichtigen) macht bewusst ella-watchdog (bash) --
dort existieren bereits die korrekten sudo/HOME/nvm-Pfade dafuer. Dieses
Skript gibt nur maschinenlesbare Anweisungen auf stdout aus:

  RECOVER\t<session_key>\t<prompt_tempfile>\t<kurzes_label>
  GIVEUP\t<session_key>\t<grund>

Erkennung: Im Gateway-Log gibt es bei einem Kontext-Ueberlauf wiederholte
Zeilen der Form
  [compaction-diag] end ... sessionKey=<key> ... trigger=budget ... outcome=failed
ohne dazwischenliegenden Erfolg. Mehrere solcher Fehlschlaege fuer dieselbe
Session in kurzer Zeit (Schwelle: siehe THRESHOLD/WINDOW_MIN) gelten als
"Session haengt fest".
"""
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
BOT_USER_HOME = os.environ.get("BOT_USER_HOME", os.path.expanduser("~"))
GW_LOG = os.path.join(BOT_USER_HOME, ".openclaw-gateway.log")
SESSIONS_DIR = os.path.join(BOT_USER_HOME, ".openclaw", "agents", "main", "sessions")
STATE_FILE = os.path.join(BOT_USER_HOME, ".ella_crash_state.json")
GEMMA_ASSIST_PY = os.path.join(BASE_DIR, "ella-gemma-assist.py")

WINDOW_MIN = 20        # Zeitfenster, in dem Fehlschlaege gezaehlt werden
THRESHOLD = 3          # ab so vielen Fehlschlaegen im Fenster: "haengt fest"
COOLDOWN_MIN = 10       # nach einer Recovery-Aktion: so lange nicht erneut auslösen
MAX_ATTEMPTS = int(os.environ.get("ELLA_WATCHDOG_MAX_RETRIES", "2"))

ANSI_RE = re.compile(r"\x1b\[\d+m")


def _strip_ansi(line):
    return ANSI_RE.sub("", line)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "log_inode": None, "log_offset": 0,
            "session_failures": {}, "recovery_attempts": {},
            "last_action": {}, "given_up": {},
        }


def save_state(state):
    d = os.path.dirname(STATE_FILE) or "."
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def read_new_lines(state):
    try:
        st = os.stat(GW_LOG)
    except FileNotFoundError:
        return []
    inode = st.st_ino
    offset = state.get("log_offset", 0)
    if state.get("log_inode") != inode or st.st_size < offset:
        offset = 0  # Log rotiert/gekuerzt -> von vorn lesen
    lines = []
    with open(GW_LOG, encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        for line in f:
            lines.append(line.rstrip("\n"))
        state["log_offset"] = f.tell()
    state["log_inode"] = inode
    return lines


def parse_failures(lines):
    """Liefert Liste von (sessionKey, ts_iso, outcome) fuer trigger=budget-Zeilen."""
    out = []
    for raw in lines:
        clean = _strip_ansi(raw)
        if "[compaction-diag] end" not in clean or "trigger=budget" not in clean:
            continue
        ts_m = re.match(r"^(?P<ts>[\d\-T:.+]+)", clean)
        sess_m = re.search(r"sessionKey=(\S+?)(?:\s|$)", clean)
        outcome_m = re.search(r"outcome=(\w+)", clean)
        if not (ts_m and sess_m and outcome_m):
            continue
        out.append((sess_m.group(1), ts_m.group("ts"), outcome_m.group(1)))
    return out


def now():
    return datetime.datetime.now().astimezone()


def parse_ts(ts):
    try:
        return datetime.datetime.fromisoformat(ts)
    except Exception:
        return None


def lookup_session_id(session_key):
    try:
        with open(os.path.join(SESSIONS_DIR, "sessions.json"), encoding="utf-8") as f:
            store = json.load(f)
        return store.get(session_key, {}).get("sessionId")
    except Exception:
        return None


def read_session_tail(session_id, max_bytes=120_000):
    path = os.path.join(SESSIONS_DIR, session_id + ".jsonl")
    try:
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            return f.read()
    except Exception:
        return None


def gemma_analyze_crash(tail_text):
    fd, tmp = tempfile.mkstemp(dir=BOT_USER_HOME, prefix=".ella_crash_tail_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(tail_text)
        proc = subprocess.run(
            ["python3", GEMMA_ASSIST_PY, "analyze-crash", tmp],
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


def main():
    state = load_state()
    lines = read_new_lines(state)
    failures = parse_failures(lines)

    cutoff = now() - datetime.timedelta(minutes=WINDOW_MIN)
    for session_key, ts, outcome in failures:
        parsed = parse_ts(ts)
        if parsed is None:
            continue
        bucket = state["session_failures"].setdefault(session_key, [])
        if outcome == "failed":
            bucket.append(ts)
        else:
            # Erfolgreiche Compaction fuer diese Session -> Zaehler zuruecksetzen
            state["session_failures"][session_key] = []

    # Alte Einträge ausserhalb des Zeitfensters wegwerfen
    for session_key in list(state["session_failures"].keys()):
        kept = []
        for ts in state["session_failures"][session_key]:
            parsed = parse_ts(ts)
            if parsed and parsed >= cutoff:
                kept.append(ts)
        if kept:
            state["session_failures"][session_key] = kept
        else:
            del state["session_failures"][session_key]

    results = []
    for session_key, ts_list in list(state["session_failures"].items()):
        if len(ts_list) < THRESHOLD:
            continue
        if state["given_up"].get(session_key):
            continue
        last_action = state["last_action"].get(session_key)
        if last_action:
            last_dt = parse_ts(last_action)
            if last_dt and (now() - last_dt) < datetime.timedelta(minutes=COOLDOWN_MIN):
                continue  # noch in Cooldown nach letzter Aktion

        attempts = state["recovery_attempts"].get(session_key, 0)
        if attempts >= MAX_ATTEMPTS:
            state["given_up"][session_key] = True
            results.append(("GIVEUP", session_key, f"{attempts}x Recovery-Versuch ohne dauerhaften Erfolg"))
            continue

        session_id = lookup_session_id(session_key)
        if not session_id:
            # Session schon anderweitig geleert/archiviert (z.B. manuell) -> nichts zu tun,
            # Zaehler zuruecksetzen statt endlos erneut zu pruefen.
            state["session_failures"][session_key] = []
            continue

        tail_text = read_session_tail(session_id)
        if not tail_text:
            state["session_failures"][session_key] = []
            continue

        prompt = gemma_analyze_crash(tail_text)
        if not prompt:
            # Gemma nicht erreichbar -> spaeter erneut versuchen, kein Attempt verbrauchen
            continue

        fd, prompt_file = tempfile.mkstemp(dir=BOT_USER_HOME, prefix=".ella_crash_prompt_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(prompt)

        label = prompt.splitlines()[0][:220] if prompt else "Kontext-Ueberlauf"
        state["recovery_attempts"][session_key] = attempts + 1
        state["last_action"][session_key] = now().isoformat()
        state["session_failures"][session_key] = []
        results.append(("RECOVER", session_key, prompt_file, label))

    save_state(state)

    for r in results:
        print("\t".join(r))


if __name__ == "__main__":
    main()
