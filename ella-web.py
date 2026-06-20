#!/usr/bin/env python3
"""
ella-web.py — Status-/Skills-/Sessions-Webseite fuer den Bot (klauski).

Zeigt: Identitaet (aus IDENTITY.md), Gateway/owltrail-Status, aktuelle
Aufgabe, installierte Skills, laufende OpenClaw-Sessions (mit Modell +
Kontextstand + Loeschen-Knopf) und einen separaten Chat gegen ein
zweites lokales Modell (Gemma-3 12B, eigene kleine Config-Datei).

Kein externes Framework, kein neuer Dependency — nur stdlib (wie owltrail.py).
"""
import datetime
import html
import json
import os
import re
import glob
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
BOT_USER_HOME = os.environ.get("BOT_USER_HOME", os.path.expanduser("~"))
WORKSPACE = os.path.join(BOT_USER_HOME, ".openclaw", "workspace")
IDENTITY_FILE = os.path.join(WORKSPACE, "IDENTITY.md")
TASK_FILE = os.path.join(BOT_USER_HOME, ".ella_task.json")
TOKEN_BUDGET_FILE = os.path.join(BOT_USER_HOME, ".ella_token_budget.json")
OWLTRAIL_PID = os.path.join(BOT_USER_HOME, ".ella_owltrail.pid")
SESSIONS_DIR = os.path.join(BOT_USER_HOME, ".openclaw", "agents", "main", "sessions")
OPENCLAW_JSON = os.path.join(BOT_USER_HOME, ".openclaw", "openclaw.json")
GEMMA3_CONFIG_FILE = os.path.join(BOT_USER_HOME, ".ella_gemma3.json")
SESSION_CLEAR_PY = os.path.join(BASE_DIR, "ella-session-clear.py")
ASSETS_DIR = os.path.join(BOT_USER_HOME, ".ella_web_assets", "klauski_states")
PLAYLIST_DIR = os.path.join(BOT_USER_HOME, ".ella_web_assets", "playlist")
GATEWAY_PORT = 18789


def resolve_openclaw_bin():
    """systemd --user Units haben kein nvm im PATH — hier selbst auflösen,
    gleiche Strategie wie ella-core (which, sonst nvm-Pfad direkt suchen)."""
    found = shutil.which("openclaw")
    if found:
        return found
    candidates = sorted(glob.glob(os.path.join(BOT_USER_HOME, ".nvm", "versions", "node", "*", "bin", "openclaw")))
    if candidates:
        return candidates[-1]
    return "openclaw"


OPENCLAW_BIN = resolve_openclaw_bin()

# openclaw ist ein Node-Skript (#!/usr/bin/env node) — ohne nvm im PATH
# findet "env node" sonst das Ubuntu-System-Node (zu alt). Eigene PATH fuer
# Subprocess-Aufrufe bauen, die das nvm-bin-Verzeichnis garantiert enthaelt.
_SUBPROCESS_ENV = dict(os.environ)
_nvm_bin_dir = os.path.dirname(OPENCLAW_BIN)
if _nvm_bin_dir and _nvm_bin_dir not in _SUBPROCESS_ENV.get("PATH", ""):
    _SUBPROCESS_ENV["PATH"] = _nvm_bin_dir + os.pathsep + _SUBPROCESS_ENV.get("PATH", "")


def _tcp_open(host, port, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def read_identity():
    data = {"name": "?", "vibe": "", "emoji": "🤖", "alcohol": None}
    try:
        text = open(IDENTITY_FILE, encoding="utf-8").read()
    except FileNotFoundError:
        return data
    m = re.search(r"\*\*Name:\*\*\s*(.+)", text)
    if m:
        data["name"] = m.group(1).strip()
    m = re.search(r"\*\*Vibe:\*\*\s*(.+)", text)
    if m:
        data["vibe"] = m.group(1).strip()
    m = re.search(r"\*\*Emoji:\*\*\s*(.+)", text)
    if m:
        data["emoji"] = m.group(1).strip()
    m = re.search(r"Aktuell:\s*\*\*(\d+)\*\*", text)
    if m:
        data["alcohol"] = int(m.group(1))
    return data


ELLA_ALCOHOL_PY = os.path.join(BASE_DIR, "ella-alcohol.py")


def add_alcohol(delta):
    """Aendert den Alkoholstand in IDENTITY.md ueber ella-alcohol.py — single
    source of truth, auch fuer die CLI (ella alcohol burn/add) genutzt, damit
    die Kurzfassung im Text nie auseinanderlaeuft."""
    try:
        out = subprocess.run(
            ["python3", ELLA_ALCOHOL_PY, IDENTITY_FILE, str(delta)],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return int(out)
    except Exception:
        return None


def read_task():
    try:
        with open(TASK_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# Tarif-Tabelle fuer die Drink-Buttons: ein Klick gibt Klauski sowohl mehr
# Alkohol (Spielerei) als auch echte Token-Gutschrift aufs Kontingent
# (umgekehrte Wirtschaft: Drinks "spendieren" dem Bot mehr Sprit zum Arbeiten).
# Feste Server-Tabelle, keine Werte vom Client — Faustregel wie beim alten
# Alkohol-Endpoint ("keine beliebigen Werte vom Client").
DRINKS = {
    "schnaps":      {"label": "🥃 Schnaps",         "price": "2 Ct",        "alcohol": 1,   "tokens": 1000},
    "bier":         {"label": "🍺 Bier",            "price": "3 Ct",        "alcohol": 2,   "tokens": 2000},
    "wodka":        {"label": "🍾 Wodkaflasche",    "price": "10 Ct",       "alcohol": 10,  "tokens": 10000},
    "kasten_bier":  {"label": "📦 Kasten Bier",     "price": "30 Ct",       "alcohol": 20,  "tokens": 50000},
    "kasten_wodka": {"label": "📦 Kasten Wodka",    "price": "49 Ct",       "alcohol": 50,  "tokens": 100000},
    "zapfhahn":     {"label": "🚰 Zapfhahn-Flatrate", "price": "9,99 €/Monat", "alcohol": 100, "flatrate": True},
}


def read_token_budget():
    try:
        with open(TOKEN_BUDGET_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("remaining"), data.get("total_consumed"), bool(data.get("flatrate"))
    except Exception:
        return None, None, False


def _render_drink_buttons(flatrate_active):
    if flatrate_active:
        return (
            '        <button class="crate cancel" onclick="cancelFlatrate()">❌ Abo kündigen<br>'
            '<span class="muted">danach wieder einzeln nachschieben</span></button>'
        )
    parts = []
    for key, d in DRINKS.items():
        is_flatrate = bool(d.get("flatrate"))
        sub = (
            f'+{d["alcohol"]} Alk · {d["tokens"]//1000}K Tok · {d["price"]}' if not is_flatrate
            else f'+100 Alk · unbegrenzt · {d["price"]}'
        )
        parts.append(
            f'<button class="crate" onclick="buyDrink(\'{key}\')">'
            f'{d["label"]}<br><span class="muted">{sub}</span></button>'
        )
    return "        " + "\n        ".join(parts)


def update_token_budget(tokens_delta=0, set_flatrate=None):
    try:
        with open(TOKEN_BUDGET_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"remaining": 0, "total_consumed": 0}
    if tokens_delta:
        data["remaining"] = (data.get("remaining") or 0) + tokens_delta
    if set_flatrate is not None:
        data["flatrate"] = set_flatrate
    d = os.path.dirname(TOKEN_BUDGET_FILE) or "."
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, TOKEN_BUDGET_FILE)
    return data


def owltrail_port():
    try:
        with open(OWLTRAIL_PID, encoding="utf-8") as f:
            lines = f.read().splitlines()
            return int(lines[1])
    except Exception:
        return 8081


_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 30


def _cached(key, fn):
    """Cacht teure 'openclaw <cmd>'-Subprocess-Aufrufe.

    Diese Aufrufe starten Node-Prozesse, die auf dieser Maschine mehrere
    Sekunden brauchen. Sie laufen NIE im Pfad eines Seitenaufrufs — die
    Seite selbst rendert sofort aus schnellen, lokalen Daten und laedt
    Skills/Sessions per JS-Fetch im Hintergrund nach (siehe /api/skills,
    /api/sessions). Ein Hintergrund-Thread (_cache_warmer) haelt den
    Cache zusaetzlich proaktiv warm, damit auch der allererste Abruf
    nach dem Start meist schon aus dem Cache kommt.
    """
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        now = time.time()
        if entry and now - entry[0] < _CACHE_TTL_SECONDS:
            return entry[1]
    result = fn()
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), result)
    return result


def _cache_warmer():
    while True:
        try:
            read_skills()
            read_sessions()
        except Exception:
            pass
        time.sleep(_CACHE_TTL_SECONDS - 5)


def read_skills():
    def _fetch():
        try:
            out = subprocess.run(
                [OPENCLAW_BIN, "skills", "list", "--json"],
                cwd=WORKSPACE, capture_output=True, text=True, timeout=20, env=_SUBPROCESS_ENV,
            ).stdout
            data = json.loads(out)
            return data.get("skills", [])
        except Exception:
            return []
    return _cached("skills", _fetch)


def read_default_model():
    try:
        with open(OPENCLAW_JSON, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "?")
    except Exception:
        return "?"


def read_sessions():
    def _fetch():
        try:
            out = subprocess.run(
                [OPENCLAW_BIN, "sessions", "--json", "--limit", "20"],
                cwd=WORKSPACE, capture_output=True, text=True, timeout=20, env=_SUBPROCESS_ENV,
            ).stdout
            data = json.loads(out)
            return data.get("sessions", [])
        except Exception:
            return []
    return _cached("sessions", _fetch)


def read_gemma3_config():
    defaults = {
        "model_id": "124",
        "model_name": "Gemma-3 12B",
        "context_cap_tokens": 32000,
        "system_prompt": "Du bist ein hilfreicher Assistent.",
    }
    try:
        with open(GEMMA3_CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        defaults.update(cfg)
    except Exception:
        pass
    return defaults


def clear_session(key):
    """Loescht/archiviert eine Session genauso wie 'ella sessions self'."""
    proc = subprocess.run(
        ["python3", SESSION_CLEAR_PY, SESSIONS_DIR, key],
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        return False
    subprocess.run(
        [OPENCLAW_BIN, "sessions", "cleanup", "--fix-missing", "--enforce"],
        cwd=WORKSPACE, capture_output=True, text=True, timeout=20, env=_SUBPROCESS_ENV,
    )
    with _CACHE_LOCK:
        _CACHE.pop("sessions", None)
    return True


def read_identity_text():
    """Rohtext von IDENTITY.md -- wird als Persona-Vorprompt fuer den
    Website-Chat verwendet, damit "Klauski fragen" auch wirklich als
    Klauski antwortet (Ton/Rechtschreibung je Alkoholstand), nicht als
    neutraler Assistent."""
    try:
        return open(IDENTITY_FILE, encoding="utf-8").read().strip()
    except FileNotFoundError:
        return None


def gemma_chat(message, history, rag_context=None):
    cfg = read_gemma3_config()
    cap_chars = int(cfg["context_cap_tokens"]) * 4  # grobe Tokens->Zeichen-Heuristik

    identity_text = read_identity_text()
    if identity_text:
        system_content = (
            identity_text
            + "\n\nDu chattest hier mit jemandem über das Status-Webinterface. "
            "Bleib in deiner Rolle (Name, Vibe, aktueller Alkoholstand oben)."
        )
    else:
        system_content = cfg["system_prompt"]
    if rag_context:
        system_content += (
            "\n\nZusätzlicher Kontext aus dem RAG-System (vor der Antwort an den "
            "Nutzer berücksichtigen, aber nur wenn er zur Frage passt):\n" + rag_context
        )

    messages = [{"role": "system", "content": system_content}]
    trimmed = list(history)
    while trimmed and sum(len(m.get("content", "")) for m in trimmed) > cap_chars:
        trimmed.pop(0)
    messages.extend(trimmed)
    messages.append({"role": "user", "content": message})

    body = json.dumps({
        "model": cfg["model_id"],
        "stream": False,
        "messages": messages,
    }).encode()

    req = urllib.request.Request(
        f"http://127.0.0.1:{owltrail_port()}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer ella"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        return f"[Fehler {e.code}: {e.read().decode(errors='replace')[:200]}]"
    except Exception as e:
        return f"[Fehler: {e}]"


RAG_CONF_FILE = os.path.join(BOT_USER_HOME, "rag.conf")
PAPERLESS_URL = "http://localhost:8005"
QDRANT_URL = "http://localhost:6333"
CLAWRAG_URL = "http://localhost:8090"
CONSUME_DIR = os.path.join(BOT_USER_HOME, "paperless", "consume")


def rag_query(project, question):
    """Fragt ClawRAG (/query) fuer ein Projekt ab -- liefert (answer, document_ids)
    oder wirft eine Exception, die der Aufrufer in eine Fehlermeldung uebersetzt.

    Timeout grosszuegig (3 Min): das Backend nutzt ein "denkendes" Modell mit
    sichtbarer Reasoning-Chain, bei echten/laengeren Dokumenten dauert eine
    Antwort durchaus 1-2 Minuten."""
    body = json.dumps({"project": project, "question": question}).encode()
    admin_secret = read_rag_conf_value("CLAWRAG_ADMIN_SECRET")
    headers = {"Content-Type": "application/json"}
    if admin_secret:
        headers["X-Admin-Secret"] = admin_secret
    req = urllib.request.Request(
        f"{CLAWRAG_URL}/query",
        data=body,
        headers=headers,
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=180)
    data = json.loads(resp.read())
    return data.get("answer", ""), data.get("document_ids", [])


def paperless_search(query):
    """Volltextsuche ueber Paperless' eigene /api/documents/?query=... --
    nutzt denselben Suchindex wie die Paperless-Weboberflaeche."""
    query = (query or "").strip()
    if not query:
        return []
    token = read_rag_conf_value("CLAWRAG_PAPERLESS_TOKEN")
    data = _http_json(
        f"{PAPERLESS_URL}/api/documents/?query={urllib.parse.quote(query)}&page_size=15",
        headers={"Authorization": f"Token {token}"} if token else {},
        timeout=10,
    )
    return [
        {"id": d["id"], "title": d.get("title") or f"Dokument {d['id']}", "created": d.get("created")}
        for d in data.get("results", [])
    ]


def fetch_paperless_download(doc_id):
    """Lädt ein Dokument von Paperless herunter (PDF/Archiv-Version) -- gibt
    (content_type, content_disposition, body_bytes) zurueck, fuer den
    Download-Proxy-Endpoint. Eigener Helper statt _http_json, weil hier
    Binärdaten + Header durchgereicht werden, nicht JSON."""
    token = read_rag_conf_value("CLAWRAG_PAPERLESS_TOKEN")
    req = urllib.request.Request(
        f"{PAPERLESS_URL}/api/documents/{doc_id}/download/",
        headers={"Authorization": f"Token {token}"} if token else {},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        disposition = resp.headers.get("Content-Disposition")
        body = resp.read()
    return content_type, disposition, body


def read_rag_conf_value(key):
    try:
        text = open(RAG_CONF_FILE, encoding="utf-8").read()
    except FileNotFoundError:
        return None
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _http_json(url, headers=None, timeout=2.5):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def read_paperless_status():
    """Live-Stand fuer die Status-Seite: Dokumentenanzahl in Paperless und
    Qdrant-Collections (= RAG-Projekte) mit Punktanzahl je Projekt.

    Postgres/Redis laufen nur containerintern (kein Host-Port gemappt) und
    sind daher von hier aus nicht direkt pingbar -- ein erfolgreicher
    Paperless-API-Call bestaetigt sie indirekt (Paperless waere ohne
    funktionierende DB/Broker nicht healthy)."""
    result = {"paperless_ok": False, "doc_count": None, "qdrant_ok": False, "collections": []}
    token = read_rag_conf_value("CLAWRAG_PAPERLESS_TOKEN")
    try:
        data = _http_json(
            f"{PAPERLESS_URL}/api/documents/?page_size=1",
            headers={"Authorization": f"Token {token}"} if token else {},
        )
        result["doc_count"] = data.get("count")
        result["paperless_ok"] = True
    except Exception:
        pass
    try:
        data = _http_json(f"{QDRANT_URL}/collections")
        names = [c["name"] for c in data.get("result", {}).get("collections", [])]
        result["qdrant_ok"] = True
        for name in sorted(names):
            try:
                info = _http_json(f"{QDRANT_URL}/collections/{name}")
                points = info.get("result", {}).get("points_count")
            except Exception:
                points = None
            result["collections"].append({"name": name, "points": points})
    except Exception:
        pass
    return result


def read_consume_status():
    """Live-Stand des Check-in-Ordners: pro Projekt-Unterordner die Anzahl
    Dateien, die dort noch liegen (= von Paperless noch nicht abgeholt).
    Leer ist der Normalzustand -- Paperless raeumt erfolgreich verarbeitete
    Dateien selbst aus dem Ordner."""
    projects = []
    try:
        entries = sorted(os.listdir(CONSUME_DIR))
    except OSError:
        return projects
    for name in entries:
        path = os.path.join(CONSUME_DIR, name)
        if name.startswith(".") or not os.path.isdir(path):
            continue
        try:
            pending = [f for f in os.listdir(path) if not f.startswith(".")]
        except OSError:
            pending = []
        projects.append({"name": name, "pending": len(pending)})
    return projects


def read_playlist():
    try:
        return sorted(f for f in os.listdir(PLAYLIST_DIR) if f.lower().endswith(".mp3"))
    except OSError:
        return []


def nearest_state_image(alcohol):
    """Rundet den Alkoholpegel (0-100) auf die naechste vorhandene 10er-Stufe."""
    if alcohol is None:
        return None
    level = max(0, min(100, round(alcohol / 10) * 10))
    path = os.path.join(ASSETS_DIR, f"klauski_{level:03d}.png")
    return level if os.path.exists(path) else None


def render_page():
    """Rendert die Seite SOFORT aus schnellen, lokalen Daten — KEINE
    'openclaw'-Subprocess-Aufrufe hier. Skills/Sessions kommen per JS-Fetch
    von /api/skills und /api/sessions, sobald sie verfuegbar sind."""
    identity = read_identity()
    task = read_task()
    gemma_cfg = read_gemma3_config()
    gw_ok = _tcp_open("127.0.0.1", GATEWAY_PORT)
    owl_ok = _tcp_open("127.0.0.1", owltrail_port())

    def status_badge(ok):
        return (
            '<span class="badge ok">● online</span>' if ok
            else '<span class="badge down">● offline</span>'
        )

    task_html = '<p class="muted">Kein aktiver Auftrag.</p>'
    flagged_session_key = ""
    flagged_session_label = ""
    if task and task.get("status") == "in_progress" and task.get("task"):
        task_kind = task.get("kind")
        if task_kind == "crash_recovery":
            kind_badge = '<span class="badge crash">🚨 Auto-Crash-Recovery</span> '
            flagged_session_label = "🚨 Crash-Recovery"
        elif task_kind == "bigloop_followup":
            kind_badge = '<span class="badge crash">🔁 Bigloop-Nachhaken</span> '
            flagged_session_label = "🔁 Nachhaken"
        else:
            kind_badge = ""
        if task_kind in ("crash_recovery", "bigloop_followup"):
            flagged_session_key = task.get("session_key") or ""
        task_html = (
            f'<p>{kind_badge}<b>📋 {html.escape(task["task"])}</b><br>'
            f'<span class="muted">seit {html.escape(task.get("started_at") or "?")}</span></p>'
        )

    alcohol = identity["alcohol"]
    alcohol_html = f'<span class="badge alc">🥃 {alcohol}</span>' if alcohol is not None else ""

    budget_remaining, budget_consumed, flatrate_active = read_token_budget()
    budget_html = ""
    if flatrate_active:
        budget_html = '<span class="badge ok">🚰 Flatrate aktiv</span>'
    elif budget_remaining is not None:
        b_class = "ok" if budget_remaining > 0 else "down"
        b_fmt = f"{budget_remaining/1000:.1f}K" if abs(budget_remaining) >= 1000 else str(budget_remaining)
        budget_html = f'<span class="badge {b_class}">🎯 {b_fmt} Token übrig</span>'

    state_level = nearest_state_image(alcohol)
    portrait_html = ""
    if state_level is not None:
        bar_color = "#5fd98a" if 30 <= alcohol <= 70 else ("#ffc56b" if 10 <= alcohol <= 90 else "#ff8080")
        portrait_html = f"""
  <div class="card portrait-card">
    <img src="/assets/klauski_{state_level:03d}.png" alt="Klauski Zustand {state_level}%" class="portrait">
    <div class="alc-bar-wrap">
      <div class="alc-label">🥃 Alkoholpegel: {alcohol}% <span class="muted">(Zustand: {state_level}%)</span>
        <button class="link-btn" onclick="soberUp()" style="margin-left:8px;">🧊 Ausnüchtern</button>
      </div>
      <div class="alc-bar"><div class="alc-bar-fill" style="width:{alcohol}%; background:{bar_color};"></div></div>
      <div class="muted" style="margin-top:4px;">0% = nüchtern/angespannt · 50% = bester Zustand · 100% = total betrunken</div>
      <div class="drink-crates">
{_render_drink_buttons(flatrate_active)}
      </div>
      <div class="muted" style="margin-top:6px;">Standard-Tarif: jedes Getränk gibt Klauski mehr Alkohol UND lädt sein Token-Kontingent auf (echte Buchung, kein reines Gimmick mehr).</div>
    </div>
  </div>"""

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    default_model = html.escape(read_default_model())

    pl = read_paperless_status()
    pl_doc_html = (
        html.escape(str(pl["doc_count"])) if pl["paperless_ok"] and pl["doc_count"] is not None
        else '<span class="muted">?</span>'
    )
    if pl["collections"]:
        coll_rows = "".join(
            f'<tr><td class="mono">{html.escape(c["name"])}</td>'
            f'<td>{c["points"] if c["points"] is not None else "?"}</td></tr>'
            for c in pl["collections"]
        )
    else:
        coll_rows = '<tr><td colspan="2" class="muted">Keine Collections.</td></tr>'

    rag_project_names = [
        c["name"][len("paperless_"):] if c["name"].startswith("paperless_") else c["name"]
        for c in pl["collections"]
    ]
    rag_select_options = '<option value="">Kein RAG</option>' + "".join(
        f'<option value="{html.escape(p)}">{html.escape(p)}</option>' for p in rag_project_names
    )

    checkin_active = bool(task and task.get("status") == "in_progress" and task.get("task"))
    checkin_status_html = (
        f'<span class="badge ok">● läuft: {html.escape(task["task"])}</span>' if checkin_active
        else '<span class="badge ok">● kein Check-in aktiv</span>'
    )
    consume_projects = read_consume_status()
    if consume_projects:
        any_pending = any(p["pending"] for p in consume_projects)
        consume_rows = "".join(
            f'<tr><td class="mono">{html.escape(p["name"])}</td>'
            f'<td>{"🟡 " + str(p["pending"]) + " wartend" if p["pending"] else "✅ leer"}</td></tr>'
            for p in consume_projects
        )
    else:
        any_pending = False
        consume_rows = '<tr><td colspan="2" class="muted">Keine Projektordner gefunden.</td></tr>'

    paperless_card = f"""
  <div class="card">
    <h3>📥 Check-in-Pipeline</h3>
    <ul>
      <li><span class="emoji">🤖</span>Bot empfängt Datei aus einer Signalgruppe<span class="desc">eine Gruppe = ein Projekt-Slug, einmal vergeben, nie geändert</span></li>
      <li><span class="emoji">📁</span>Datei landet in <span class="mono">~/paperless/consume/&lt;projekt&gt;/</span><span class="desc">neuer Ordnername = automatisch neues Projekt, keine Registrierung nötig</span></li>
      <li><span class="emoji">📄</span>Paperless holt sie ab: OCR (Deutsch) + Tagging nach Ordnername<span class="desc">Tesseract + unpaper, PSM 6, Subdir-as-Tags</span></li>
      <li><span class="emoji">🔗</span>Workflow-Webhook an ClawRAG <span class="mono">/index</span><span class="desc">Projekt wird aus dem Tag aufgelöst, neue Collection bei Bedarf automatisch angelegt</span></li>
      <li><span class="emoji">🧠</span>Embedding + Ablage in Qdrant-Collection <span class="mono">paperless_&lt;projekt&gt;</span><span class="desc">danach per /query durchsuchbar</span></li>
    </ul>
    <h4 style="margin:14px 0 4px;">Aktueller Check-in</h4>
    <p>{checkin_status_html}</p>
    <h4 style="margin:14px 0 4px;">Check-in-Ordner <span class="mono">~/paperless/consume/</span></h4>
    <table>
      <tr><th>Projekt</th><th>Status</th></tr>
      {consume_rows}
    </table>
    <p class="muted" style="margin-top:6px;">{"⚠️ Es liegen Dateien, die Paperless noch nicht abgeholt hat." if any_pending else "Normalzustand: leer — Paperless holt neue Dateien sofort selbst ab und räumt sie danach."}</p>
  </div>

  <div class="card">
    <h3>🗄️ Datenbanken &amp; Paperless-Stand</h3>
    <div>{status_badge(pl["paperless_ok"])} Paperless-API &nbsp; {status_badge(pl["qdrant_ok"])} Qdrant</div>
    <p style="margin-top:10px;">📄 Dokumente in Paperless: <b>{pl_doc_html}</b></p>
    <table>
      <tr><th>Datenbank</th><th>Zweck</th></tr>
      <tr><td>PostgreSQL</td><td>Paperless-Metadaten (Dokumente, Tags, Workflows) — nur containerintern, kein Host-Port</td></tr>
      <tr><td>Redis</td><td>Celery-Task-Queue für Paperless (OCR-Jobs etc.) — nur containerintern</td></tr>
      <tr><td>Qdrant</td><td>Vektor-Speicher fürs RAG-System, eine Collection pro Projekt</td></tr>
    </table>
    <p class="muted" style="margin-top:8px;">PostgreSQL/Redis sind nicht direkt von hier aus pingbar (kein gemappter Host-Port) — ein erfolgreicher Paperless-API-Call bestätigt sie indirekt.</p>
    <h4 style="margin:14px 0 4px;">RAG-Projekte (Qdrant-Collections)</h4>
    <table>
      <tr><th>Collection</th><th>Punkte (Chunks)</th></tr>
      {coll_rows}
    </table>
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(identity['name'])} — Status</title>
<style>
  body {{ background:#0f1115; color:#e6e6e6; font-family:-apple-system,Segoe UI,Roboto,sans-serif; max-width:880px; margin:40px auto; padding:0 20px; }}
  h1 {{ font-size:1.8em; margin-bottom:0; }}
  .vibe {{ color:#9aa0a6; margin-top:4px; }}
  .card {{ background:#1a1d24; border:1px solid #2a2e37; border-radius:10px; padding:18px 20px; margin:18px 0; }}
  .badge {{ display:inline-block; padding:2px 10px; border-radius:12px; font-size:0.85em; margin-right:8px; }}
  .badge.ok {{ background:#0d3321; color:#5fd98a; }}
  .badge.down {{ background:#3a1414; color:#ff8080; }}
  .badge.alc {{ background:#3a2a0d; color:#ffc56b; }}
  .badge.crash {{ background:#3a1414; color:#ff8080; }}
  tr.flagged {{ background:#2a1414; }}
  .muted {{ color:#8a8f98; font-size:0.9em; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  li {{ padding:8px 0; border-bottom:1px solid #22262f; }}
  li:last-child {{ border-bottom:none; }}
  .emoji {{ margin-right:6px; }}
  .desc {{ display:block; color:#8a8f98; font-size:0.85em; margin-top:2px; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.9em; }}
  td, th {{ padding:6px 4px; border-bottom:1px solid #22262f; text-align:left; }}
  .mono {{ font-family:monospace; font-size:0.85em; }}
  form {{ margin:0; display:inline; }}
  button {{ background:#2a2e37; color:#e6e6e6; border:1px solid #3a3f4a; border-radius:6px; padding:3px 8px; cursor:pointer; }}
  button:hover {{ background:#3a3f4a; }}
  #chat-log {{ max-height:300px; overflow-y:auto; margin-bottom:10px; }}
  .msg {{ padding:6px 10px; border-radius:8px; margin:4px 0; max-width:85%; }}
  .msg.user {{ background:#1f3a5f; margin-left:auto; text-align:right; }}
  .msg.bot {{ background:#22262f; }}
  #chat-input {{ width:100%; box-sizing:border-box; background:#0f1115; color:#e6e6e6; border:1px solid #2a2e37; border-radius:6px; padding:8px; }}
  .portrait-card {{ display:flex; gap:20px; align-items:center; }}
  .portrait {{ width:160px; height:160px; object-fit:cover; border-radius:10px; border:1px solid #2a2e37; }}
  .alc-bar-wrap {{ flex:1; }}
  .alc-label {{ font-weight:bold; margin-bottom:6px; }}
  .alc-bar {{ background:#22262f; border-radius:8px; height:14px; overflow:hidden; }}
  .alc-bar-fill {{ height:100%; transition:width 0.3s; }}
  .drink-crates {{ display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }}
  .crate:disabled {{ opacity:0.35; cursor:not-allowed; }}
  .crate:disabled:hover {{ background:#22262f; border-color:#3a3f4a; }}
  .link-btn {{ background:none; border:none; color:#8a8f98; text-decoration:underline; cursor:pointer; font-size:0.85em; padding:0; }}
  .link-btn:hover {{ color:#e6e6e6; }}
  .crate {{ flex:1 1 100px; background:#22262f; border:1px solid #3a3f4a; border-radius:8px; padding:8px 6px; text-align:center; font-size:0.85em; cursor:pointer; color:#e6e6e6; }}
  .crate:hover {{ background:#2a2e37; border-color:#5fd98a; }}
  .crate:active {{ transform:scale(0.97); }}
  footer {{ color:#5a5f68; font-size:0.8em; margin-top:30px; text-align:center; }}
</style>
</head>
<body>
  <h1>{html.escape(identity['emoji'])} {html.escape(identity['name'])}</h1>
  <div class="vibe">{html.escape(identity['vibe'])}</div>
  <div class="card" id="playlist-card" style="display:none;">
    <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
      <span>🎵</span>
      <span id="playlist-track" class="muted">—</span>
      <audio id="playlist-player" controls style="flex:1; min-width:200px;"></audio>
    </div>
  </div>
{portrait_html}
  <div class="card">
    <div>{status_badge(gw_ok)} Gateway &nbsp; {status_badge(owl_ok)} owltrail &nbsp; {alcohol_html} &nbsp; {budget_html}</div>
    <div class="muted" style="margin-top:8px;">OpenClaw-Modell (Standard): {default_model}</div>
  </div>

  <div class="card">
    <h3>Aktuelle Aufgabe</h3>
    {task_html}
  </div>

  <div class="card">
    <h3>💬 Klauski fragen <span class="muted">({html.escape(gemma_cfg['model_name'])}, Kontext-Cap {gemma_cfg['context_cap_tokens']} Tok.)</span></h3>
    <div class="muted" style="margin-bottom:10px;">
      RAG-System: <select id="rag-select">{rag_select_options}</select>
      <span class="muted">— wenn gesetzt, wird die Frage zuerst dort gesucht; der Treffer wandert ins Vorprompt von Klauski.</span>
    </div>
    <div id="chat-log"></div>
    <input id="chat-input" type="text" placeholder="Nachricht eingeben und Enter drücken…">
  </div>
{paperless_card}
  <div class="card">
    <h3>🔎 Dokumente durchsuchen &amp; herunterladen</h3>
    <input id="doc-search-input" type="text" placeholder="Suchbegriff eingeben und Enter drücken…">
    <ul id="doc-search-results"></ul>
  </div>

  <div class="card">
    <h3 id="sessions-title">OpenClaw-Sessions <span class="muted">(lädt…)</span></h3>
    <table id="sessions-table">
      <tr><th>Typ</th><th>Session</th><th>Modell</th><th>Kontext</th><th>Alter</th><th></th></tr>
      <tr><td colspan="6" class="muted">⏳ Lädt (kann beim ersten Mal einige Sekunden dauern)…</td></tr>
    </table>
  </div>

  <div class="card">
    <h3 id="skills-title">Skills <span class="muted">(lädt…)</span></h3>
    <ul id="skills-ready-list"><li class="muted">⏳ Lädt…</li></ul>
  </div>

  <div class="card">
    <h3 class="muted">Weitere installierte Skills (noch nicht aktiv)</h3>
    <ul id="skills-not-ready-list"><li class="muted">⏳ Lädt…</li></ul>
  </div>

  <footer>Stand: {now}</footer>

<script>
function esc(s) {{
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}}

const FLAGGED_SESSION_KEY = {json.dumps(flagged_session_key)};
const FLAGGED_SESSION_LABEL = {json.dumps(flagged_session_label)};

async function loadSessions() {{
  const title = document.getElementById('sessions-title');
  const table = document.getElementById('sessions-table');
  try {{
    const res = await fetch('/api/sessions');
    const sessions = await res.json();
    title.innerHTML = 'OpenClaw-Sessions (' + sessions.length + ')';
    let rows = '<tr><th>Typ</th><th>Session</th><th>Modell</th><th>Kontext</th><th>Alter</th><th></th></tr>';
    for (const s of sessions) {{
      const key = s.key || '?';
      const keyShort = key.length > 44 ? key.slice(0, 41) + '...' : key;
      const ctxUsed = s.totalTokens || 0;
      const ctxMax = s.contextTokens || 0;
      const pct = ctxMax ? Math.round(ctxUsed / ctxMax * 100) + '%' : '?';
      const ageMin = Math.floor((s.ageMs || 0) / 60000);
      const isFlagged = FLAGGED_SESSION_KEY && key === FLAGGED_SESSION_KEY;
      const rowClass = isFlagged ? ' class="flagged"' : '';
      const flagMark = isFlagged ? ' <span class="badge crash">' + esc(FLAGGED_SESSION_LABEL) + '</span>' : '';
      rows += '<tr' + rowClass + '><td>' + esc(s.kind || '?') + '</td><td class="mono">' + esc(keyShort) + flagMark + '</td>' +
        '<td>' + esc(String(s.model || '?')) + '</td><td>' + ctxUsed + '/' + ctxMax + ' (' + pct + ')</td>' +
        '<td>' + ageMin + 'm</td><td><form method="post" action="/api/session/clear" ' +
        'onsubmit="return confirm(\\'Session wirklich löschen?\\');">' +
        '<input type="hidden" name="key" value="' + esc(key) + '">' +
        '<button type="submit">🗑️</button></form></td></tr>';
    }}
    table.innerHTML = rows;
  }} catch (err) {{
    title.innerHTML = 'OpenClaw-Sessions <span class="muted">(Fehler beim Laden)</span>';
  }}
}}

async function loadSkills() {{
  const title = document.getElementById('skills-title');
  const readyList = document.getElementById('skills-ready-list');
  const notReadyList = document.getElementById('skills-not-ready-list');
  try {{
    const res = await fetch('/api/skills');
    const skills = await res.json();
    const ready = skills.filter(s => s.eligible);
    const notReady = skills.filter(s => !s.eligible);
    title.innerHTML = 'Skills (' + ready.length + ' aktiv / ' + skills.length + ' gesamt)';
    const row = s => '<li><span class="emoji">' + esc(s.emoji || '🧩') + '</span> <b>' +
      esc(s.name || '?') + '</b><span class="desc">' + esc(s.description || '') + '</span></li>';
    readyList.innerHTML = ready.map(row).join('') || '<li class="muted">Keine.</li>';
    notReadyList.innerHTML = notReady.slice(0, 20).map(row).join('') || '<li class="muted">Keine.</li>';
  }} catch (err) {{
    title.innerHTML = 'Skills <span class="muted">(Fehler beim Laden)</span>';
  }}
}}

loadSessions();
loadSkills();

async function loadPlaylist() {{
  const card = document.getElementById('playlist-card');
  const trackLabel = document.getElementById('playlist-track');
  const player = document.getElementById('playlist-player');
  try {{
    const res = await fetch('/api/playlist');
    const files = await res.json();
    if (!files.length) return;
    card.style.display = 'block';

    let idx = parseInt(localStorage.getItem('ella_playlist_idx') || '0', 10);
    if (idx >= files.length) idx = 0;
    const resumeTime = parseFloat(localStorage.getItem('ella_playlist_time') || '0');

    // Bei nur einem Track: natives loop-Attribut (robuster als ein
    // ended-Handler, der sich selbst neu antriggert). Bei mehreren Tracks
    // wird die ganze Liste per ended-Handler durchlaufen und am Ende wieder
    // von vorn gestartet -- ebenfalls endlos.
    player.loop = (files.length === 1);

    function playTrack(i, startAt) {{
      idx = i % files.length;
      localStorage.setItem('ella_playlist_idx', idx);
      trackLabel.textContent = files[idx].replace(/[.]mp3$/i, '');
      player.src = '/audio/' + encodeURIComponent(files[idx]);
      if (startAt) player.currentTime = startAt;
      player.play().catch(() => {{
        trackLabel.textContent += ' (Autoplay blockiert — startet beim ersten Klick irgendwo auf der Seite)';
      }});
    }}

    if (!player.loop) {{
      player.addEventListener('ended', () => playTrack(idx + 1));
    }}
    player.addEventListener('timeupdate', () => {{
      localStorage.setItem('ella_playlist_time', player.currentTime);
    }});

    playTrack(idx, resumeTime);

    // Browser blockieren Autoplay mit Ton ohne vorherige Nutzer-Interaktion.
    // Fallback: beim allerersten Klick/Tastendruck irgendwo auf der Seite
    // automatisch starten, statt dass der Nutzer gezielt ▶ druecken muss.
    const resumeOnInteraction = () => {{
      if (player.paused) player.play().catch(() => {{}});
      document.removeEventListener('click', resumeOnInteraction);
      document.removeEventListener('keydown', resumeOnInteraction);
    }};
    document.addEventListener('click', resumeOnInteraction);
    document.addEventListener('keydown', resumeOnInteraction);
  }} catch (err) {{
    // Kein Playlist-Ordner / keine Dateien -> Karte einfach versteckt lassen
  }}
}}

loadPlaylist();

async function buyDrink(drink) {{
  try {{
    await fetch('/api/drink', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{drink}}),
    }});
    location.reload();
  }} catch (err) {{
    alert('Fehler: ' + err);
  }}
}}

async function soberUp() {{
  try {{
    await fetch('/api/sober', {{ method: 'POST' }});
    location.reload();
  }} catch (err) {{
    alert('Fehler: ' + err);
  }}
}}

async function cancelFlatrate() {{
  try {{
    await fetch('/api/flatrate/cancel', {{ method: 'POST' }});
    location.reload();
  }} catch (err) {{
    alert('Fehler: ' + err);
  }}
}}

let history = [];
const log = document.getElementById('chat-log');
const input = document.getElementById('chat-input');

function addMsg(role, text) {{
  const div = document.createElement('div');
  div.className = 'msg ' + (role === 'user' ? 'user' : 'bot');
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}}

const ragSelect = document.getElementById('rag-select');

input.addEventListener('keydown', async (e) => {{
  if (e.key !== 'Enter' || !input.value.trim()) return;
  const message = input.value.trim();
  const project = ragSelect.value;
  input.value = '';
  addMsg('user', message);

  let ragContext = null;
  if (project) {{
    addMsg('bot', '🔍 durchsuche RAG-Projekt "' + project + '"…');
    const ragPlaceholder = log.lastChild;
    try {{
      const ragRes = await fetch('/api/rag-query', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{project, question: message}}),
      }});
      const ragData = await ragRes.json();
      if (ragData.error) {{
        ragPlaceholder.textContent = '⚠️ RAG-Fehler: ' + ragData.error + ' (frage trotzdem ohne Kontext)';
      }} else {{
        ragContext = ragData.answer;
        const ids = ragData.document_ids || [];
        ragPlaceholder.textContent = '🔍 RAG-Antwort: ' + ragData.answer + ' ';
        if (ids.length) {{
          const docsSpan = document.createElement('span');
          docsSpan.textContent = '(Quellen: ';
          ids.forEach((id, i) => {{
            const a = document.createElement('a');
            a.href = '/api/paperless-download/' + id;
            a.textContent = 'Dok. ' + id;
            a.target = '_blank';
            a.style.color = '#5fd98a';
            docsSpan.appendChild(a);
            if (i < ids.length - 1) docsSpan.appendChild(document.createTextNode(', '));
          }});
          docsSpan.appendChild(document.createTextNode(')'));
          ragPlaceholder.appendChild(docsSpan);
        }}
      }}
    }} catch (err) {{
      ragPlaceholder.textContent = '⚠️ RAG nicht erreichbar: ' + err + ' (frage trotzdem ohne Kontext)';
    }}
  }}

  addMsg('bot', '…');
  const placeholder = log.lastChild;
  try {{
    const res = await fetch('/api/gemma-chat', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{message, history, rag_context: ragContext}}),
    }});
    const data = await res.json();
    placeholder.textContent = data.reply;
    history.push({{role: 'user', content: message}});
    history.push({{role: 'assistant', content: data.reply}});
  }} catch (err) {{
    placeholder.textContent = '[Fehler: ' + err + ']';
  }}
}});

const docSearchInput = document.getElementById('doc-search-input');
const docSearchResults = document.getElementById('doc-search-results');

docSearchInput.addEventListener('keydown', async (e) => {{
  if (e.key !== 'Enter' || !docSearchInput.value.trim()) return;
  const q = docSearchInput.value.trim();
  docSearchResults.innerHTML = '<li class="muted">⏳ Suche…</li>';
  try {{
    const res = await fetch('/api/paperless-search?q=' + encodeURIComponent(q));
    const data = await res.json();
    if (data.error) {{
      docSearchResults.innerHTML = '<li class="muted">⚠️ Fehler: ' + esc(data.error) + '</li>';
      return;
    }}
    const results = data.results || [];
    if (!results.length) {{
      docSearchResults.innerHTML = '<li class="muted">Keine Treffer.</li>';
      return;
    }}
    docSearchResults.innerHTML = results.map(d =>
      '<li><a href="/api/paperless-download/' + d.id + '" target="_blank" style="color:#5fd98a;">⬇ ' +
      esc(d.title) + '</a><span class="desc">' + esc(d.created || '') + ' · Dok.-ID ' + d.id + '</span></li>'
    ).join('');
  }} catch (err) {{
    docSearchResults.innerHTML = '<li class="muted">⚠️ Fehler: ' + esc(String(err)) + '</li>';
  }}
}});
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/assets/"):
            self._serve_asset(self.path[len("/assets/"):])
            return
        if self.path.startswith("/audio/"):
            self._serve_audio(self.path[len("/audio/"):])
            return
        if self.path == "/api/playlist":
            self._send_json(read_playlist())
            return
        if self.path == "/api/skills":
            self._send_json(read_skills())
            return
        if self.path == "/api/sessions":
            self._send_json(read_sessions())
            return
        if self.path.startswith("/api/paperless-search"):
            parsed = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
            try:
                self._send_json({"results": paperless_search(q)})
            except Exception as e:
                self._send_json({"error": str(e)})
            return
        if self.path.startswith("/api/paperless-download/"):
            m = re.fullmatch(r"/api/paperless-download/(\d+)", self.path)
            if not m:
                self.send_response(404)
                self.end_headers()
                return
            try:
                content_type, disposition, body = fetch_paperless_download(int(m.group(1)))
            except Exception as e:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(str(e).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            if disposition:
                self.send_header("Content-Disposition", disposition)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = render_page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_asset(self, filename):
        # Nur exakt erwartete Dateinamen erlauben (klauski_NNN.png) — keine
        # Pfad-Traversal-Moeglichkeit, da kein "/" oder ".." durchkommt.
        if not re.fullmatch(r"klauski_\d{3}\.png", filename):
            self.send_response(404)
            self.end_headers()
            return
        path = os.path.join(ASSETS_DIR, filename)
        if not os.path.isfile(path):
            self.send_response(404)
            self.end_headers()
            return
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def _serve_audio(self, filename):
        # Nur Dateinamen ohne "/" oder ".." erlauben (keine Pfad-Traversal),
        # und nur .mp3 -- die Datei muss tatsaechlich im Playlist-Ordner liegen.
        filename = urllib.parse.unquote(filename)
        if "/" in filename or ".." in filename or not filename.lower().endswith(".mp3"):
            self.send_response(404)
            self.end_headers()
            return
        path = os.path.join(PLAYLIST_DIR, filename)
        if not os.path.isfile(path):
            self.send_response(404)
            self.end_headers()
            return
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""

        if self.path == "/api/session/clear":
            fields = urllib.parse.parse_qs(raw.decode())
            key = (fields.get("key") or [""])[0]
            clear_session(key)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if self.path == "/api/drink":
            try:
                payload = json.loads(raw)
                key = payload.get("drink", "")
            except Exception:
                key = ""
            drink = DRINKS.get(key)
            if not drink:
                self._send_json({"error": "ungueltiges Getraenk"})
                return
            new_alcohol = add_alcohol(drink["alcohol"]) if drink.get("alcohol") else None
            if drink.get("flatrate"):
                budget = update_token_budget(set_flatrate=True)
            else:
                budget = update_token_budget(tokens_delta=drink.get("tokens", 0))
            self._send_json({
                "alcohol": new_alcohol,
                "remaining": budget.get("remaining"),
                "flatrate": bool(budget.get("flatrate")),
            })
            return

        if self.path == "/api/flatrate/cancel":
            budget = update_token_budget(set_flatrate=False)
            self._send_json({"flatrate": bool(budget.get("flatrate"))})
            return

        if self.path == "/api/sober":
            # -100 garantiert 0 unabhaengig vom aktuellen Stand (Clamp in ella-alcohol.py)
            new_alcohol = add_alcohol(-100)
            self._send_json({"alcohol": new_alcohol})
            return

        if self.path == "/api/gemma-chat":
            try:
                payload = json.loads(raw)
                reply = gemma_chat(
                    payload.get("message", ""),
                    payload.get("history") or [],
                    rag_context=payload.get("rag_context") or None,
                )
            except Exception as e:
                reply = f"[Fehler: {e}]"
            body = json.dumps({"reply": reply}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/rag-query":
            try:
                payload = json.loads(raw)
                project = payload.get("project", "")
                question = payload.get("question", "")
                answer, document_ids = rag_query(project, question)
                self._send_json({"answer": answer, "document_ids": document_ids})
            except Exception as e:
                self._send_json({"error": str(e)})
            return

        self.send_response(404)
        self.end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
    threading.Thread(target=_cache_warmer, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    print(f"ella-web läuft auf Port {port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
