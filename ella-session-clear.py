#!/usr/bin/env python3
"""ella-session-clear.py — Loescht/archiviert die Historie einer einzelnen
OpenClaw-Session sicher, ohne Gateway-Neustart und ohne andere Sessions
zu beruehren.

Aufruf: ella-session-clear.py <sessions_dir> <session_key_oder_id>
Gibt bei Erfolg den session_key auf stdout aus, sonst Fehlermeldung auf
stderr + exit 1. Die Transkript-Dateien werden umbenannt (nicht geloescht),
damit nichts unwiderbringlich verloren geht.
"""
import datetime
import json
import os
import sys


def main():
    sessions_dir = sys.argv[1]
    target = sys.argv[2]
    store_path = os.path.join(sessions_dir, "sessions.json")

    with open(store_path, encoding="utf-8") as f:
        store = json.load(f)

    key = None
    session_id = None
    if target in store:
        key = target
        session_id = store[target].get("sessionId")
    else:
        for k, v in store.items():
            if v.get("sessionId") == target:
                key, session_id = k, target
                break

    if not session_id:
        print(f"Keine Session gefunden fuer: {target}", file=sys.stderr)
        sys.exit(1)

    ts = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    for suffix in (".jsonl", ".trajectory.jsonl", ".trajectory-path.json"):
        src = os.path.join(sessions_dir, session_id + suffix)
        if os.path.exists(src):
            os.rename(src, src + f".manual-reset.{ts}")

    print(key)


if __name__ == "__main__":
    main()
