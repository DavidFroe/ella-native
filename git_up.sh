#!/bin/bash
# ================================================================
# ELLA-PI Git Upload — Push lokalen Stand zu GitHub
# ================================================================
# Bügelt den Remote-Master mit dem lokalen Stand platt.
# Config-Dateien werden NICHT eingecheckt (via .gitignore).

set -e
cd "$(dirname "$(readlink -f "$0")")"

echo -e "\033[0;34m🚀 ELLA-PI Git Upload\033[0m"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

BRANCH=$(git branch --show-current 2>/dev/null || echo "main")

# Alle Scripts ausführbar machen
chmod +x ella ella-* 2>/dev/null || true

# Alles einpacken (.gitignore schützt Configs & Logs)
git add -A

# Status zeigen
CHANGES=$(git diff --cached --stat)
if [ -z "$CHANGES" ]; then
    echo "ℹ️  Keine Änderungen zum Hochladen."
    exit 0
fi

echo -e "\033[0;33m📋 Änderungen:\033[0m"
echo "$CHANGES"
echo ""

# Commit & Force Push
MSG="Ella-Pi Sync: $(date +'%Y-%m-%d %H:%M:%S')"
git commit -m "$MSG"
git push origin "$BRANCH" --force

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "\033[0;32m✅ Upload auf '$BRANCH' erledigt!\033[0m"
