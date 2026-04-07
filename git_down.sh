#!/bin/bash
# ================================================================
# ELLA-PI Git Download — Pull von GitHub (überbügelt lokal)
# ================================================================
# Holt den aktuellen Stand von GitHub und überschreibt alles Lokale.
# Config-Dateien bleiben erhalten (via .gitignore).

set -e
cd "$(dirname "$(readlink -f "$0")")"

echo -e "\033[0;34m🛬 ELLA-PI Git Download\033[0m"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

BRANCH=$(git branch --show-current 2>/dev/null || echo "main")

# Warnung
echo -e "\033[0;33m⚠️  Alle lokalen Änderungen werden überschrieben!\033[0m"
echo -n "Fortfahren? [j/N]: "
read -r CONFIRM
if [[ ! "$CONFIRM" =~ ^[jJyY]$ ]]; then
    echo "Abgebrochen."
    exit 0
fi

# Lokalen Stand plattmachen
echo "📥 Hole Stand von origin/$BRANCH..."
git fetch --all
git reset --hard "origin/$BRANCH"
git clean -fd

# Scripts ausführbar machen
chmod +x ella ella-* *.sh 2>/dev/null || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "\033[0;32m✅ Download von '$BRANCH' erledigt!\033[0m"
echo "   Tipp: ella restart"
