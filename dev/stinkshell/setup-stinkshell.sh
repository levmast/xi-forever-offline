#!/bin/bash
# Stinkshell relay on the hub server (run as root): installs the relay as a service on 127.0.0.1:54300 and puts it behind
# Caddy as chat.xiforever.com (Caddy gets the certificate). Run again any time to update the relay.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
id stinkshell >/dev/null 2>&1 || useradd --system --home /var/lib/stinkshell --shell /usr/sbin/nologin stinkshell
mkdir -p /opt/stinkshell /var/lib/stinkshell
install -m 644 "$HERE/stinkshell_relay.py" /opt/stinkshell/stinkshell_relay.py
chown stinkshell:stinkshell /var/lib/stinkshell
chmod 700 /var/lib/stinkshell
cat > /etc/systemd/system/stinkshell.service <<'UNIT'
[Unit]
Description=Stinkshell chat relay (XI: Forever Offline)
After=network.target

[Service]
User=stinkshell
ExecStart=/usr/bin/python3 /opt/stinkshell/stinkshell_relay.py --port 54300 --data /var/lib/stinkshell
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/stinkshell
ProtectHome=true
PrivateTmp=true
MemoryMax=300M

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable stinkshell >/dev/null 2>&1
systemctl restart stinkshell
mkdir -p /etc/caddy/sites
cat > /etc/caddy/sites/stinkshell.caddy <<'SITE'
chat.xiforever.com {
	reverse_proxy 127.0.0.1:54300
}
SITE
caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 || { rm -f /etc/caddy/sites/stinkshell.caddy; echo "Caddy refused the settings; the chat site was taken out again."; exit 1; }
systemctl reload caddy
sleep 3
echo "relay: $(systemctl is-active stinkshell)"
curl -s http://127.0.0.1:54300/health; echo
curl -s --max-time 20 https://chat.xiforever.com/health; echo
echo "Owner code (type /login CODE once in the Stinkshell window; keep it private):"
cat /var/lib/stinkshell/owner.txt
