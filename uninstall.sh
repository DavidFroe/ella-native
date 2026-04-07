#!/bin/bash
# ================================================================
# ELLA-PI UNINSTALLER (v10.0)
# ================================================================
# Entfernt Ella komplett vom System.
# /home/ella mit Config-Daten bleibt erhalten für Reinstall.

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

echo -e "${RED}${BOLD}🗑️  ELLA-PI DEINSTALLATION${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${YELLOW}⚠️  WARNUNG: Ella wird vollständig entfernt.${NC}"
echo -e "   Folgendes bleibt erhalten:"
echo -e "   • $HOME/ (Home-Verzeichnis)"
echo -e "   • $HOME/.config/openclaw-kibot/ (Configs)"
echo -e "   • $HOME/.openclaw/ (Gateway-Config & Auth)"
echo ""
echo -n "Fortfahren? [j/N]: "
read -r CONFIRM
if [[ ! "$CONFIRM" =~ ^[jJ]$ ]]; then
    echo "Abgebrochen."
    exit 0
fi

echo ""

# ---------------------------------------------------------------
# 1. ALLE ELLA-PROZESSE STOPPEN
# ---------------------------------------------------------------
echo -e "${CYAN}⏹️  1. Prozesse stoppen...${NC}"

# owltrail stoppen
OWLTRAIL_DIR="$(dirname "$(readlink -f "$0")")"/../owltrail
if [ -f "$OWLTRAIL_DIR/.owltrail.pid" ]; then
    PID=$(cat "$OWLTRAIL_DIR/.owltrail.pid")
    kill "$PID" 2>/dev/null && echo "   owltrail gestoppt (PID $PID)"
    rm -f "$OWLTRAIL_DIR/.owltrail.pid"
fi
pkill -f "owltrail_server" 2>/dev/null || true

# Gateway stoppen
OPENCLAW_BIN=$(which openclaw 2>/dev/null)
if [ -n "$OPENCLAW_BIN" ]; then
    $OPENCLAW_BIN gateway stop 2>/dev/null || true
fi
pkill -f "openclaw gateway" 2>/dev/null || true

echo -e "   ${GREEN}✅ Alle Prozesse gestoppt.${NC}"

# ---------------------------------------------------------------
# 2. SYSTEMD SERVICE ENTFERNEN
# ---------------------------------------------------------------
echo -e "\n${CYAN}⚙️  2. Systemd Service entfernen...${NC}"
if [ -f /etc/systemd/system/ella-pi.service ]; then
    sudo systemctl stop ella-pi.service 2>/dev/null || true
    sudo systemctl disable ella-pi.service 2>/dev/null || true
    sudo rm -f /etc/systemd/system/ella-pi.service
    sudo systemctl daemon-reload
    echo -e "   ${GREEN}✅ Service entfernt.${NC}"
else
    echo -e "   ℹ️  Kein Service vorhanden."
fi

# ---------------------------------------------------------------
# 3. SYMLINKS ENTFERNEN
# ---------------------------------------------------------------
echo -e "\n${CYAN}🔗 3. Symlinks entfernen...${NC}"
sudo rm -f /usr/local/bin/ella 2>/dev/null && echo "   /usr/local/bin/ella entfernt" || true
rm -f "$HOME/.local/bin/owltrail" 2>/dev/null && echo "   ~/.local/bin/owltrail entfernt" || true
rm -f "$HOME/.local/bin/owl" 2>/dev/null && echo "   ~/.local/bin/owl entfernt" || true
echo -e "   ${GREEN}✅ Symlinks bereinigt.${NC}"

# ---------------------------------------------------------------
# 4. OWLTRAIL DEINSTALLIEREN
# ---------------------------------------------------------------
echo -e "\n${CYAN}🦉 4. owltrail entfernen...${NC}"
if [ -d "$OWLTRAIL_DIR" ]; then
    # VENV und generierte Dateien entfernen
    rm -rf "$OWLTRAIL_DIR/venv" 2>/dev/null
    rm -rf "$OWLTRAIL_DIR/__pycache__" 2>/dev/null
    rm -rf "$OWLTRAIL_DIR/.pytest_cache" 2>/dev/null
    rm -f "$OWLTRAIL_DIR/owltrail" 2>/dev/null
    rm -f "$OWLTRAIL_DIR/owltrail.log" 2>/dev/null
    rm -f "$OWLTRAIL_DIR/.owltrail.pid" 2>/dev/null
    echo -e "   ${GREEN}✅ owltrail bereinigt (Quellcode bleibt).${NC}"
else
    echo -e "   ℹ️  owltrail nicht gefunden."
fi

# ---------------------------------------------------------------
# 5. ELLA-NATIVE VERZEICHNIS BEREINIGEN
# ---------------------------------------------------------------
echo -e "\n${CYAN}📁 5. Ella-Native bereinigen...${NC}"
ELLA_DIR="$(dirname "$(readlink -f "$0")")"
rm -f "$ELLA_DIR"/*.log "$ELLA_DIR"/*.bak "$ELLA_DIR"/*.tmp 2>/dev/null
rm -f "$ELLA_DIR/doctor.log" "$ELLA_DIR/doctor_out.txt" 2>/dev/null
echo -e "   ${GREEN}✅ Temporäre Dateien entfernt.${NC}"

# Optional: Gesamtes Verzeichnis entfernen
echo ""
echo -n "   Ella-Native Quellcode auch löschen? ($ELLA_DIR) [j/N]: "
read -r DEL_SRC
if [[ "$DEL_SRC" =~ ^[jJ]$ ]]; then
    echo -e "   ${RED}Lösche $ELLA_DIR...${NC}"
    rm -rf "$ELLA_DIR"
    echo -e "   ${GREEN}✅ Quellcode gelöscht.${NC}"
else
    echo -e "   ℹ️  Quellcode bleibt erhalten."
fi

# ---------------------------------------------------------------
# FERTIG
# ---------------------------------------------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}${BOLD}✅ ELLA-PI Deinstallation abgeschlossen.${NC}"
echo ""
echo -e "Erhalten geblieben:"
echo -e "  $HOME/.config/openclaw-kibot/  (OpenClaw Config)"
echo -e "  $HOME/.openclaw/               (Gateway Config & Auth)"
echo ""
echo -e "Reinstall: git clone + ./install.sh"
