#!/usr/bin/env python3
"""ella-alcohol.py — Liest/aendert Klauskis Alkoholstand in IDENTITY.md.

Single Source of Truth fuer die Logik (Web-UI und CLI rufen beide dieses
Skript auf, damit die Kurzfassung neben dem Wert nie auseinanderlaeuft).

Aufruf:
  ella-alcohol.py <identity_md_path> show          -> druckt aktuellen Wert, keine Aenderung
  ella-alcohol.py <identity_md_path> <delta:int>    -> aendert um delta (0-100 geklemmt), druckt neuen Wert
"""
import re
import sys

STAGE_NOTES = {
    0: "stocknüchtern, angespannt",
    10: "fast nüchtern, wach",
    20: "mild entspannt",
    30: "angenehm entspannt",
    40: "warmherzig, aufgekratzt",
    50: "Bestzustand! 🥃",
    60: "angeheitert",
    70: "sichtlich betrunken",
    80: "ziemlich betrunken",
    90: "sehr betrunken, kaum kohärent",
    100: "Delirium, weggetreten",
}


def nearest_stage_note(value):
    level = max(0, min(100, round(value / 10) * 10))
    return STAGE_NOTES[level]


def main():
    path = sys.argv[1]
    mode = sys.argv[2]

    with open(path, encoding="utf-8") as f:
        text = f.read()

    m = re.search(r"Aktuell:\s*\*\*(\d+)\*\*(?:\s*\([^)]*\))?", text)
    if not m:
        print("FEHLER: Pattern nicht gefunden", file=sys.stderr)
        sys.exit(1)

    current = int(m.group(1))

    if mode == "show":
        print(current)
        return

    delta = int(mode)
    new_value = max(0, min(100, current + delta))
    note = nearest_stage_note(new_value)
    replacement = f"Aktuell: **{new_value}** ({note} 🥃)"
    new_text = text[:m.start()] + replacement + text[m.end():]

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)

    print(new_value)


if __name__ == "__main__":
    main()
