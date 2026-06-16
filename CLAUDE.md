# Kontext: klauski OpenClaw Setup

Du läufst als root auf dem Rechner 11.0.0.15 (klaus-Aspire-A315-53).

## Offene Aufgabe: Telegram Gruppen
Der Bot antwortet im Direktchat aber NICHT in Gruppen.

**Was bereits erledigt ist:**
- BotFather Group Privacy deaktiviert
- openclaw.json hat `"requireMention": false` für `"*"` Gruppen
- Gateway läuft als nohup (PID in `/home/klauski/.openclaw-gateway.pid`)

**Was zu tun ist:**
1. Gateway-Logs prüfen: `/home/klauski/.openclaw-gateway.log`
2. Telegram-Config prüfen: `/home/klauski/.openclaw/credentials/`
3. openclaw.json prüfen: `/home/klauski/.openclaw/openclaw.json`
4. Problem finden und fixen
5. Gateway neu starten:
   `sudo -u klauski bash -c 'kill $(cat ~/.openclaw-gateway.pid) 2>/dev/null; export XDG_RUNTIME_DIR=/run/user/1000 && nohup openclaw gateway > ~/.openclaw-gateway.log 2>&1 & echo $! > ~/.openclaw-gateway.pid'`

## Nützliche Infos
- klauski Passwort: 121212
- owlAPI läuft auf 11.0.0.1:4040 (OpenAI-kompatibel, PropellerA Modelle IDs 120-199)
- ella-native liegt in /home/david/ella-native (Management-Tool für OpenClaw)
- Node 22 / openclaw via nvm bei klauski
