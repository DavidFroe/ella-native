#!/usr/bin/env python3
"""ella-task.py — Master-Task-Speicher für ella watchdog.

Aufruf: ella-task.py <mode> <path> [arg...]
Alle Werte kommen ausschliesslich über argv (nie über Shell-Interpolation
in den Python-Quelltext) — so bleiben Sonderzeichen in Aufgabentexten sicher.
"""
import json
import os
import sys
import tempfile
import datetime

EMPTY = {
    "task": None,
    "session_key": None,
    "status": "none",
    "started_at": None,
    "last_heartbeat": None,
    "recovered_at": None,
    "retry_count": 0,
    "kind": None,
    "last_nudge_at": None,
}


def load(path):
    if not os.path.exists(path):
        return dict(EMPTY)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(EMPTY)
        merged.update(data)
        return merged
    except Exception:
        return dict(EMPTY)


def save(path, data):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def main():
    mode = sys.argv[1]
    path = sys.argv[2]
    rest = sys.argv[3:]

    if mode == "set":
        desc = rest[0] if len(rest) > 0 else ""
        session = rest[1] if len(rest) > 1 and rest[1] else None
        kind = rest[2] if len(rest) > 2 and rest[2] else None
        save(path, {
            "task": desc, "session_key": session, "status": "in_progress",
            "started_at": now_iso(), "last_heartbeat": now_iso(), "recovered_at": None,
            "retry_count": 0, "kind": kind, "last_nudge_at": now_iso(),
        })
        print("OK")

    elif mode == "heartbeat":
        data = load(path)
        if data.get("status") == "in_progress":
            data["last_heartbeat"] = now_iso()
            save(path, data)
            print("OK")
        else:
            print("NO_ACTIVE_TASK")

    elif mode == "done":
        data = load(path)
        data["status"] = "done"
        data["last_heartbeat"] = now_iso()
        save(path, data)
        print("OK")

    elif mode == "clear":
        save(path, dict(EMPTY))
        print("OK")

    elif mode == "retry":
        # Watchdog stößt die abgestürzte Aufgabe erneut an — Heartbeat/Status
        # frisch, retry_count hoch, damit eine Crash-Loop-Aufgabe nicht endlos
        # neu gestartet wird (siehe MAX_RETRIES in ella-watchdog).
        data = load(path)
        data["retry_count"] = int(data.get("retry_count") or 0) + 1
        data["status"] = "in_progress"
        data["last_heartbeat"] = now_iso()
        data["recovered_at"] = now_iso()
        data["last_nudge_at"] = now_iso()
        save(path, data)
        print(data["retry_count"])

    elif mode == "fail":
        # Endgültig aufgeben — keine weiteren automatischen Versuche mehr.
        data = load(path)
        data["status"] = "failed"
        data["recovered_at"] = now_iso()
        save(path, data)
        print("OK")

    elif mode == "show":
        data = load(path)
        status = data.get("status", "none")
        print(f"STATUS:{status}")
        print(f"RETRY_COUNT:{data.get('retry_count', 0)}")
        print(f"KIND:{data.get('kind') or ''}")
        print(f"LAST_NUDGE_AT:{data.get('last_nudge_at') or ''}")
        if status == "in_progress" and data.get("task"):
            hb = data.get("last_heartbeat")
            age_min = -1
            if hb:
                delta = datetime.datetime.now() - datetime.datetime.fromisoformat(hb)
                age_min = int(delta.total_seconds() // 60)
            print(f"TASK:{data.get('task')}")
            print(f"SESSION:{data.get('session_key') or '?'}")
            print(f"STARTED:{data.get('started_at') or '?'}")
            print(f"HEARTBEAT_AGE_MIN:{age_min}")

    else:
        print(f"Unbekannter Modus: {mode}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
