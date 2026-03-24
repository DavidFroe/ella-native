#!/bin/bash
# ELLA-PI NATIVE INSTALLER (v10.0 Slim-Version)
BLUE='\033[0;34m'; GREEN='\033[0;32m'; NC='\033[0m'

echo -e "${BLUE}🦉 ELLA-PI: Native Installation (v10.0 Slim)${NC}"

# 1. DEPENDENCIES (Nur das Nötigste)
echo -e "\n📦 1. System-Check..."
sudo apt-get update
sudo apt-get install -y procps psmisc htop curl
echo -e "${GREEN}✅ System-Tools bereit.${NC}"

# 2. LINKING (ella command überall verfügbar)
echo -e "\n🔗 2. Erstelle Symlinks..."
# Wir nutzen den aktuellen Ordner als Quelle
CURRENT_DIR=$(pwd)
CURRENT_USER=$(whoami)
sudo ln -sf "$CURRENT_DIR/ella" /usr/local/bin/ella
chmod +x "$CURRENT_DIR/ella"*
echo -e "${GREEN}✅ Befehl 'ella' ist nun unter /usr/local/bin verfügbar.${NC}"

# 3. SYSTEMD SERVICE SETUP
echo -e "\n⚙️  3. Aktiviere Ella-Pi systemd-Service..."
# Pfade im Service-File auf den aktuellen Ordner anpassen
sed -i "s|{{INSTALL_DIR}}|$CURRENT_DIR|g" "$CURRENT_DIR/ella-pi.service"
sed -i "s|{{USER}}|$CURRENT_USER|g" "$CURRENT_DIR/ella-pi.service"
sudo cp "$CURRENT_DIR/ella-pi.service" /etc/systemd/system/ella-pi.service
sudo systemctl daemon-reload
echo -e "${GREEN}✅ Service konfiguriert.${NC}"

echo -e "\n${GREEN}✨ FERTIG! Probiere jetzt einfach 'ella' im Terminal.${NC}"
