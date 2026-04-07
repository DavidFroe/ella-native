#!/usr/bin/env python3
"""
ella-owltrail-runner.py — Startet owltrail.py als Hintergrundprozess.

Wird von ella-owltrail als daemonisierter Prozess gestartet.
Schreibt PID + genutzten Port in die PID-Datei (je eine Zeile).
"""

import argparse
import json
import logging
import os
import signal
import socket
import sys
import time

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, BASE_DIR)

import owltrail


def find_free_port(start_port: int) -> int:
    """Gibt den ersten freien Port ab start_port zurück (max. +20)."""
    for port in range(start_port, start_port + 20):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start_port  # letzte Chance — wird beim Start scheitern


def update_openclaw_configs(new_port: int, old_port: int) -> None:
    """Aktualisiert openclaw JSON-Configs wenn der Port gewechselt hat."""
    if new_port == old_port:
        return

    old_key = f"custom-localhost-{old_port}"
    new_key = f"custom-localhost-{new_port}"
    old_url = f"http://localhost:{old_port}/v1"
    new_url = f"http://localhost:{new_port}/v1"

    paths = [
        os.path.expanduser("~/.config/openclaw-kibot/.openclaw/openclaw.json"),
        os.path.expanduser("~/.openclaw/openclaw.json"),
    ]

    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)

            changed = False
            providers = data.get("models", {}).get("providers", {})
            if old_key in providers:
                providers[new_key] = providers.pop(old_key)
                providers[new_key]["baseUrl"] = new_url
                changed = True

            defs = data.get("agents", {}).get("defaults", {})
            if defs.get("model", {}).get("primary") == f"{old_key}/auto":
                defs["model"]["primary"] = f"{new_key}/auto"
                changed = True
            if f"{old_key}/auto" in defs.get("models", {}):
                defs["models"][f"{new_key}/auto"] = defs["models"].pop(f"{old_key}/auto")
                changed = True

            if changed:
                with open(path, "w") as f:
                    json.dump(data, f, indent=4)
                logging.getLogger("owltrail").info(
                    "openclaw config aktualisiert: %s (Port %d→%d)", path, old_port, new_port
                )
        except Exception as e:
            logging.getLogger("owltrail").warning("openclaw config update fehlgeschlagen (%s): %s", path, e)


def main() -> None:
    p = argparse.ArgumentParser(description="owltrail Proxy Daemon")
    p.add_argument("--conf", default=os.path.join(BASE_DIR, "owltrail.conf"),
                   help="Pfad zur owltrail.conf")
    p.add_argument("--log",  default=os.path.expanduser("~/.ella_owltrail.log"),
                   help="Pfad zur Log-Datei")
    p.add_argument("--pid",  default=os.path.expanduser("~/.ella_owltrail.pid"),
                   help="Pfad zur PID-Datei")
    args = p.parse_args()

    owltrail.setup_logging(args.log, verbose=False)
    log = logging.getLogger("owltrail")

    cfg       = owltrail.load_conf(args.conf)
    conf_port = int(cfg.get("listen_port", 8081))
    port      = find_free_port(conf_port)

    if port != conf_port:
        log.warning("Port %d belegt — weiche auf Port %d aus", conf_port, port)
        update_openclaw_configs(port, conf_port)

    # PID-Datei schreiben: Zeile 1 = PID, Zeile 2 = Port
    with open(args.pid, "w") as f:
        f.write(f"{os.getpid()}\n{port}\n")

    proxy = owltrail.OwlTrailProxy(conf_file=args.conf)
    proxy.start(port=port)

    log.info(
        "owltrail gestartet: Port=%d  User=%s  QuiteQue=%s:%s",
        port,
        cfg.get("username", "?"),
        cfg.get("server_ip", "?"),
        cfg.get("quiteque_port", "?"),
    )

    def _shutdown(sig, frame):
        log.info("owltrail wird gestoppt (Signal %d)…", sig)
        proxy.stop()
        try:
            os.remove(args.pid)
        except FileNotFoundError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Hauptschleife — hält den Prozess am Leben
    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
