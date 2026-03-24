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
# 5. OWLTRAIL INSTALLIEREN
# ---------------------------------------------------------------
echo -e "\n${CYAN}🦉 5. owltrail Proxy prüfen...${NC}"
OWLTRAIL_DIR="$(dirname "$BASE_DIR")/owltrail"
if [ -d "$OWLTRAIL_DIR" ] && [ -f "$OWLTRAIL_DIR/install.sh" ]; then
    echo -n "   owltrail gefunden. Installieren? [J/n]: "
    read -r INSTALL_OWL
    if [[ ! "$INSTALL_OWL" =~ ^[nN]$ ]]; then
        bash "$OWLTRAIL_DIR/install.sh"
    fi
else
    echo -e "   ${GREY}owltrail nicht gefunden ($OWLTRAIL_DIR). Überspringe.${NC}"
fi

# ---------------------------------------------------------------
# 6. ELLA.CONF
# ---------------------------------------------------------------
if [ ! -f "$BASE_DIR/ella.conf" ]; then
    echo "OWLTRAIL_PORT=${OWL_PORT:-8081}" > "$BASE_DIR/ella.conf"
fi

# ---------------------------------------------------------------
# FERTIG
# ---------------------------------------------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}${BOLD}✅ ELLA-PI Installation abgeschlossen!${NC}"
echo ""
echo -e "Nächste Schritte:"
echo -e "  ${CYAN}ella start${NC}           Ella-Pi starten"
echo -e "  ${CYAN}ella status${NC}          Status prüfen"
echo -e "  ${CYAN}ella help${NC}            Alle Befehle"
echo -e "  ${CYAN}ella owltrail test${NC}   owltrail testen"
echo ""
