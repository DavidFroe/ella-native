#!/bin/bash
# ================================================================
# ELLA-PI NATIVE INSTALLER (v10.0 Master-Setup)
# ================================================================

# --- FARBEN ---
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BLUE}${BOLD}🦉 ELLA-PI: Native Installation (v10.0)${NC}"
echo -e "${GREY}------------------------------------------------------------${NC}"

# 1. DEPENDENCIES (Raspberry Pi OS / Debian)
echo -e "\n📦 1. Installiere System-Abhängigkeiten (sudo)..."
sudo apt-get update
sudo apt-get install -y nodejs npm git python3 python3-pip curl pgrep fuser htop
echo -e "${GREEN}✅ Abhängigkeiten installiert.${NC}"

# 2. OPENCLAW SETUP (Global via npm)
echo -e "\n🚀 2. Installiere OpenClaw & ClawDBot (npm global)..."
# Verhindere Berechtigungsfehler bei globaler Installation
mkdir -p "$HOME/.npm-global"
npm config set prefix "$HOME/.npm-global"
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> "$HOME/.bashrc"
source "$HOME/.bashrc"

npm install -g openclaw clawdbot 2>/dev/null
echo -e "${GREEN}✅ OpenClaw global installiert.${NC}"

# 3. LINKING (ella command überall verfügbar)
echo -e "\n🔗 3. Erstelle Symlinks (sudo /usr/local/bin)..."
# Wir linken das Hauptskript in den globalen Pfad
sudo ln -sf "$HOME/ella/ella" /usr/local/bin/ella
sudo chmod +x "$HOME/ella/ella"
# Auch die Hilfsskripte ausführbar machen
chmod +x "$HOME/ella/ella-"*
echo -e "${GREEN}✅ Befehl 'ella' ist nun überall verfügbar.${NC}"

# 4. SYSTEMD SERVICE SETUP
echo -e "\n⚙️  4. Aktiviere Ella-Pi systemd-Service..."
# Pfad im Service-File anpassen, falls nötig
sed -i "s|/home/david|/home/$USER|g" "$HOME/ella/ella-pi.service"
sudo cp "$HOME/ella/ella-pi.service" /etc/systemd/system/ella-pi.service
sudo systemctl daemon-reload
sudo systemctl enable ella-pi.service
echo -e "${GREEN}✅ Service aktiviert (Ella-Pi startet beim Booten).${NC}"

# 5. INITIALIZATION
echo -e "\n🚀 5. Starte Ella-Pi zum ersten Mal..."
sudo systemctl start ella-pi.service
sleep 3

# 6. HELLO WORLD
echo -e "\n${GREY}------------------------------------------------------------${NC}"
echo -e "${GREEN}${BOLD}✨ INSTALLATION ABGESCHLOSSEN!${NC}"
echo -e "${CYAN}Ella sagt:${NC} \"Hallo Papa! Ich bin jetzt auf dem Pi zu Hause.\""
echo -e "${YELLOW}Tipp:${NC} Nutze 'ella --status' um alles zu prüfen."

# Falls Telegram konfiguriert ist, sende eine Nachricht
if [ -f "$HOME/.config/openclaw-kibot/.openclaw/openclaw.json" ]; then
    ella "Ich bin wach, Papa! Ella v10.0 Native läuft auf dem Pi." 2>/dev/null
fi
