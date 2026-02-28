# 🦉 ELLA-PI (v10.0 Native Edition)

```text
       , _ ,
      ( o o )
     /  \ /  \
    / //   \\ \
   / (_     _) \
  /   '---'   \
  '-----------'
```

## Die native KI-Zentrale für den Raspberry Pi

**ELLA-PI** ist die "Bare Metal" Evolution des Ella-Systems. Sie befreit das KI-Gedächtnis von Containern (Podman/Distrobox) und bietet maximale Performance und Stabilität nativ auf dem Raspberry Pi OS.

---

## ⚡ Schnellstart: Installation auf dem Pi

Auf einem frischen Raspberry Pi (Empf: Debian 12 / Bookworm) genügt ein Kommando nach dem Klonen:

```bash
git clone https://github.com/david/ella.git
cd ella
chmod +x ella-install-native.sh
./ella-install-native.sh
```

---

## 🌍 GLOBETROTTER: Umzug von Bazzite zu Pi

Wenn du bereits eine Instanz auf deinem Hauptrechner (Bazzite/Fedora) hast, kannst du sie mit einem Befehl teleportieren:

```bash
ella --migrate
```

*Folge den Anweisungen im Terminal (IP & User des Pi eingeben).*

---

## ⚙️ Core Funktionen (v10.0 Master-CLI)

| Befehl | Aktion | Warum du ihn brauchst |
| :--- | :--- | :--- |
| `ella --start` | **Master-Boot** | Startet Gateway, owlTrail Proxy & bereinigt die Ports. |
| `ella --status` | **Deep-Scan** | Zeigt den Live-Status aller KI-Prozesse und Systemlast. |
| `ella --health` | **Self-Healing** | Scannt nach Fehlern und behebt sie automatisch. |
| `ella --backup` | **Memory-Pack** | Sichert deine gesamte KI-Konfiguration (Gedächtnis). |
| `ella --context` | **Brain-Size** | Passt das Kontext-Fenster (8k bis 32k) dynamisch an. |

---

## 🛠️ System-Integration

Ella-Pi ist als **systemd Service** konzipiert. Sie startet beim Booten deines Pi automatisch alle nötigen Schnittstellen (Telegram, WhatsApp, LLM-Bridge).

- **Service-Name:** `ella-pi.service`
- **Port-Mapping:** Gateway (18789), owlTrail (8081)

---

## 🛡️ Projekt Antigravity

Dieses Repository ist Teil des Projekts *Antigravity* – Ziel ist ein völlig autonomes, selbstheilendes KI-Gedächtnis für 2026.

**"Ich bin wach, Papa!"** – *Ella v10.0*
