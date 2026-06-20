#!/bin/bash
# ================================================================
# ELLA-PI INSTALLER (v10.0)
# ================================================================
# Installiert Ella-Pi auf einem frischen System.
# Bestehende Config-Daten werden erkannt und optional beibehalten.

set -e
BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
RED='\033[0;31m'; CYAN='\033[0;36m'; GREY='\033[0;90m'
BOLD='\033[1m'; NC='\033[0m'

BASE_DIR="$( cd "$( dirname "$(readlink -f "${BASH_SOURCE[0]}")" )" &> /dev/null && pwd )"
cd "$BASE_DIR"

echo -e "${BLUE}${BOLD}🦉 ELLA-PI INSTALLER v10.0${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ---------------------------------------------------------------
# 1. SYSTEM-ABHÄNGIGKEITEN
# ---------------------------------------------------------------
echo -e "\n${CYAN}📦 1. System-Abhängigkeiten prüfen...${NC}"
DEPS="procps psmisc htop curl python3 python3-venv jq"
MISSING=""
for dep in $DEPS; do
    if ! dpkg -s "$dep" &>/dev/null; then
        MISSING="$MISSING $dep"
    fi
done
if [ -n "$MISSING" ]; then
    echo -e "   Installiere:$MISSING"
    sudo apt-get update -qq
    sudo apt-get install -y $MISSING -qq
fi
echo -e "   ${GREEN}✅ Alle Abhängigkeiten vorhanden.${NC}"

# ---------------------------------------------------------------
# 2. SCRIPTS AUSFÜHRBAR MACHEN
# ---------------------------------------------------------------
echo -e "\n${CYAN}🔧 2. Scripts vorbereiten...${NC}"
chmod +x ella ella-* *.sh 2>/dev/null || true
echo -e "   ${GREEN}✅ Alle Scripts ausführbar.${NC}"

# ---------------------------------------------------------------
# 3. ELLA BEFEHL SYSTEMWEIT VERFÜGBAR MACHEN
# ---------------------------------------------------------------
echo -e "\n${CYAN}🔗 3. 'ella' Befehl einrichten...${NC}"
sudo ln -sf "$BASE_DIR/ella" /usr/local/bin/ella
echo -e "   ${GREEN}✅ 'ella' ist jetzt überall verfügbar.${NC}"

# ---------------------------------------------------------------
# 4. OPENCLAW CONFIG
# ---------------------------------------------------------------
echo -e "\n${CYAN}⚙️  4. OpenClaw Konfiguration...${NC}"

KIBOT_CONFIG="$HOME/.config/openclaw-kibot/.openclaw/openclaw.json"
GW_CONFIG="$HOME/.openclaw/openclaw.json"

# Prüfen ob Config schon vorhanden
CONFIG_EXISTS=false
if [ -f "$KIBOT_CONFIG" ] || [ -f "$GW_CONFIG" ]; then
    CONFIG_EXISTS=true
fi

if [ "$CONFIG_EXISTS" = true ]; then
    echo -e "   ${YELLOW}⚠️  Bestehende Konfiguration gefunden.${NC}"
    echo -n "   Config beibehalten? [J/n]: "
    read -r KEEP_CONFIG
    if [[ "$KEEP_CONFIG" =~ ^[nN]$ ]]; then
        echo -e "   ${YELLOW}Config wird überschrieben...${NC}"
        CONFIG_EXISTS=false
    else
        echo -e "   ${GREEN}✅ Bestehende Config wird beibehalten.${NC}"
    fi
fi

if [ "$CONFIG_EXISTS" = false ]; then
    echo -e "\n   ${BOLD}🔧 Neue Konfiguration erstellen:${NC}"

    # owlAPI URL
    echo -n "   owlAPI URL [http://localhost:4040]: "
    read -r OWLAPI_URL
    OWLAPI_URL="${OWLAPI_URL:-http://localhost:4040}"

    # owltrail Port
    echo -n "   owltrail Port [8081]: "
    read -r OWL_PORT
    OWL_PORT="${OWL_PORT:-8081}"

    # Gateway Port
    echo -n "   Gateway Port [18789]: "
    read -r GW_PORT
    GW_PORT="${GW_PORT:-18789}"

    # Gateway Token generieren
    GW_TOKEN=$(openssl rand -hex 24 2>/dev/null || head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 48)

    # Kibot Config erstellen
    mkdir -p "$(dirname "$KIBOT_CONFIG")"
    cat > "$KIBOT_CONFIG" << EOJSON
{
    "models": {
        "providers": {
            "custom-localhost-${OWL_PORT}": {
                "api": "openai-completions",
                "baseUrl": "http://localhost:${OWL_PORT}/v1",
                "models": [{"id": "auto", "name": "auto"}]
            }
        }
    },
    "agents": {
        "defaults": {
            "model": {"primary": "custom-localhost-${OWL_PORT}/auto"},
            "models": {"custom-localhost-${OWL_PORT}/auto": {}},
            "compaction": {"mode": "safeguard"},
            "maxConcurrent": 4,
            "subagents": {"maxConcurrent": 8}
        }
    },
    "gateway": {
        "auth": {"token": "${GW_TOKEN}"},
        "remote": {"token": "${GW_TOKEN}"}
    }
}
EOJSON

    # Gateway Config erstellen
    mkdir -p "$(dirname "$GW_CONFIG")"
    cat > "$GW_CONFIG" << EOJSON
{
    "models": {
        "providers": {
            "custom-localhost-${OWL_PORT}": {
                "api": "openai-completions",
                "baseUrl": "http://localhost:${OWL_PORT}/v1",
                "models": [{"id": "auto", "name": "auto"}]
            }
        }
    },
    "agents": {
        "defaults": {
            "model": {"primary": "custom-localhost-${OWL_PORT}/auto"},
            "models": {"custom-localhost-${OWL_PORT}/auto": {}},
            "compaction": {"mode": "safeguard"},
            "maxConcurrent": 4,
            "subagents": {"maxConcurrent": 8}
        }
    },
    "gateway": {
        "mode": "local",
        "auth": {"mode": "token", "token": "${GW_TOKEN}"}
    }
}
EOJSON

    # Auth Profile (Dummy-Key für owltrail)
    AUTH_DIR="$HOME/.openclaw/agents/main/agent"
    mkdir -p "$AUTH_DIR"
    AUTH_FILE="$AUTH_DIR/auth-profiles.json"
    if [ ! -f "$AUTH_FILE" ]; then
        cat > "$AUTH_FILE" << EOJSON
{
    "version": 1,
    "profiles": {
        "custom-localhost-${OWL_PORT}:default": {
            "type": "api_key",
            "provider": "custom-localhost-${OWL_PORT}",
            "key": "owltrail-local"
        }
    },
    "usageStats": {}
}
EOJSON
    fi

    echo -e "   ${GREEN}✅ Konfiguration erstellt.${NC}"
    echo -e "   ${GREY}   Gateway Token: ${GW_TOKEN:0:12}...${NC}"
fi

# ---------------------------------------------------------------
# 5. NODE.JS >= 22 SICHERSTELLEN (openclaw-Voraussetzung)
# ---------------------------------------------------------------
echo -e "\n${CYAN}⬡  5. Node.js prüfen...${NC}"
NODE_OK=false
if command -v node &>/dev/null; then
    NODE_MAJOR=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
    if [ "${NODE_MAJOR:-0}" -ge 22 ] 2>/dev/null; then
        echo -e "   ${GREEN}✅ Node.js $(node --version) vorhanden.${NC}"
        NODE_OK=true
    else
        echo -e "   ${YELLOW}⚠️  Node.js $(node --version) zu alt (benötigt: v22+).${NC}"
    fi
else
    echo -e "   ${YELLOW}⚠️  Node.js nicht gefunden.${NC}"
fi

if [ "$NODE_OK" = false ]; then
    echo -e "   ${CYAN}Installiere Node.js 22 via NodeSource...${NC}"
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - 2>&1 | grep -E '(error|warn|OK)' || true
    sudo apt-get install -y nodejs -qq
    NODE_VER=$(node --version 2>/dev/null)
    echo -e "   ${GREEN}✅ Node.js ${NODE_VER} installiert.${NC}"
fi

# ---------------------------------------------------------------
# 6. OPENCLAW INSTALLIEREN (falls fehlt)
# ---------------------------------------------------------------
echo -e "\n${CYAN}🐾 6. OpenClaw prüfen...${NC}"
if command -v openclaw &>/dev/null; then
    OC_VER=$(openclaw --version 2>/dev/null | head -1)
    echo -e "   ${GREEN}✅ openclaw vorhanden: ${OC_VER}${NC}"
else
    echo -e "   ${YELLOW}⚠️  openclaw nicht gefunden.${NC}"
    echo -n "   openclaw installieren? [J/n]: "
    read -r INSTALL_OC
    if [[ ! "$INSTALL_OC" =~ ^[nN]$ ]]; then
        echo -e "   ${CYAN}Installiere openclaw (offizieller Installer)...${NC}"
        if curl -fsSL https://openclaw.ai/install.sh | bash; then
            # Installer legt binary meist in ~/.local/bin oder /usr/local/bin
            # PATH für aktuelle Session aktualisieren
            export PATH="$HOME/.local/bin:$PATH"
            if command -v openclaw &>/dev/null; then
                OC_VER=$(openclaw --version 2>/dev/null | head -1)
                echo -e "   ${GREEN}✅ openclaw installiert: ${OC_VER}${NC}"
            else
                echo -e "   ${YELLOW}⚠️  openclaw installiert — bitte Shell neu starten oder 'source ~/.bashrc'.${NC}"
            fi
        else
            echo -e "   ${RED}❌ openclaw Installation fehlgeschlagen.${NC}"
            echo -e "   ${GREY}   Manuell: curl -fsSL https://openclaw.ai/install.sh | bash${NC}"
        fi
    else
        echo -e "   ${GREY}openclaw übersprungen — kann später nachinstalliert werden:${NC}"
        echo -e "   ${GREY}   curl -fsSL https://openclaw.ai/install.sh | bash${NC}"
    fi
fi

# Gateway-Service einrichten (einmalig nötig)
echo -e "\n${CYAN}🛰️  6b. OpenClaw Gateway einrichten...${NC}"
if command -v openclaw &>/dev/null; then
    GW_STATUS=$(openclaw gateway status 2>&1 || true)
    if echo "$GW_STATUS" | grep -qi "disabled\|not installed\|not found\|install"; then
        echo -e "   ${CYAN}Richte openclaw Gateway-Service ein...${NC}"
        openclaw gateway install 2>&1 | tail -5
        echo -e "   ${GREEN}✅ Gateway-Service eingerichtet.${NC}"
    else
        echo -e "   ${GREEN}✅ Gateway-Service bereits eingerichtet.${NC}"
    fi
else
    echo -e "   ${GREY}openclaw nicht verfügbar — Gateway-Setup übersprungen.${NC}"
fi

# ---------------------------------------------------------------
# 7. OWLTRAIL KONFIGURIEREN
# ---------------------------------------------------------------
echo -e "\n${CYAN}🦉 7. owltrail Konfiguration...${NC}"
OWLTRAIL_CONF="$BASE_DIR/owltrail.conf"

if [ -f "$OWLTRAIL_CONF" ]; then
    echo -e "   ${YELLOW}⚠️  Bestehende owltrail.conf gefunden.${NC}"
    echo -n "   Beibehalten? [J/n]: "
    read -r KEEP_OWL
    if [[ "$KEEP_OWL" =~ ^[nN]$ ]]; then
        rm -f "$OWLTRAIL_CONF"
    fi
fi

if [ ! -f "$OWLTRAIL_CONF" ]; then
    echo -e "\n   ${BOLD}🔧 owltrail Verbindung konfigurieren:${NC}"

    echo -n "   QuiteQue Server-IP   [192.168.188.20]: "
    read -r OWL_SRV_IP
    OWL_SRV_IP="${OWL_SRV_IP:-192.168.188.20}"

    echo -n "   QuiteQue Port        [7077]: "
    read -r OWL_QQ_PORT
    OWL_QQ_PORT="${OWL_QQ_PORT:-7077}"

    echo -n "   owltrail Listen-Port [${OWL_PORT:-8081}]: "
    read -r OWL_LISTEN
    OWL_LISTEN="${OWL_LISTEN:-${OWL_PORT:-8081}}"

    echo -n "   Benutzername (für QuiteQue-Priorisierung) [ella]: "
    read -r OWL_USER
    OWL_USER="${OWL_USER:-ella}"

    cat > "$OWLTRAIL_CONF" << EOWL
{
  "server_ip": "${OWL_SRV_IP}",
  "quiteque_port": ${OWL_QQ_PORT},
  "listen_port": ${OWL_LISTEN},
  "username": "${OWL_USER}",
  "model_id": "auto",
  "timeout": 1800
}
EOWL

    # openclaw-Configs ebenfalls auf den gewählten Port anpassen
    OWL_PORT="$OWL_LISTEN"

    echo -e "   ${GREEN}✅ owltrail.conf erstellt.${NC}"
fi

# owltrail Bibliothek prüfen
if [ -f "$BASE_DIR/owltrail.py" ]; then
    echo -e "   ${GREEN}✅ owltrail.py (Bibliothek) vorhanden.${NC}"
else
    echo -e "   ${RED}❌ owltrail.py fehlt in $BASE_DIR — bitte Repository neu klonen.${NC}"
fi

# ---------------------------------------------------------------
# 8. ELLA.CONF
# ---------------------------------------------------------------
if [ ! -f "$BASE_DIR/ella.conf" ]; then
    echo "OWLTRAIL_PORT=${OWL_PORT:-8081}" > "$BASE_DIR/ella.conf"
fi

# ---------------------------------------------------------------
# 9. STATUS-WEBSEITE, TOKEN-KONTINGENT & WATCHDOG
# ---------------------------------------------------------------
echo -e "\n${CYAN}🌐 9. Status-Webseite, Token-Kontingent & Watchdog...${NC}"

# Asset-Ordner fuer Portraits/Playlist anlegen (leer, fuellt sich bei Bedarf)
mkdir -p "$HOME/.ella_web_assets/klauski_states" "$HOME/.ella_web_assets/playlist"

# Token-Kontingent initialisieren (Kostenkontrolle fuer Output-Token des Bots,
# siehe "ella owltrail budget show/set/add")
if [ ! -f "$HOME/.ella_token_budget.json" ]; then
    echo '{"remaining": 56000, "total_consumed": 0}' > "$HOME/.ella_token_budget.json"
    echo -e "   ${GREEN}✅ Token-Kontingent mit 56.000 Token initialisiert.${NC}"
fi

echo -n "   Status-Webseite (Port 8088, zeigt Status/Skills/Sessions/Token-Kontingent) als Autostart-Service einrichten? [J/n]: "
read -r INSTALL_WEB
if [[ ! "$INSTALL_WEB" =~ ^[nN]$ ]]; then
    bash "$BASE_DIR/ella-web" install
fi

echo -n "   Watchdog (erkennt hängende Aufgaben + Kontext-Überlauf, prüft alle 5 Min.) als Timer einrichten? [J/n]: "
read -r INSTALL_WD
if [[ ! "$INSTALL_WD" =~ ^[nN]$ ]]; then
    bash "$BASE_DIR/ella-watchdog" install
fi

# ---------------------------------------------------------------
# FERTIG
# ---------------------------------------------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}${BOLD}✅ ELLA-PI Installation abgeschlossen!${NC}"
echo ""
echo -e "Nächste Schritte:"
echo -e "  ${CYAN}ella owltrail start${NC}  owltrail Proxy starten"
echo -e "  ${CYAN}ella owltrail test${NC}   Verbindung zu QuiteQue testen"
echo -e "  ${CYAN}ella start${NC}           Ella-Pi starten"
echo -e "  ${CYAN}ella status${NC}          Status prüfen"
echo -e "  ${CYAN}ella help${NC}            Alle Befehle"
echo -e "  ${CYAN}ella web status${NC}      Status-Webseite prüfen (http://localhost:8088/)"
echo -e "  ${CYAN}ella owltrail budget show${NC}  Token-Kontingent prüfen"
echo -e "  ${CYAN}ella watchdog status${NC} Watchdog-Status prüfen"
echo ""
echo -e "${GREY}Für eine separate Bot-User-Einrichtung (Admin verwaltet einen eigenen${NC}"
echo -e "${GREY}Bot-Account): ella.conf.example nach ella.conf kopieren und BOT_USER setzen.${NC}"
echo ""
