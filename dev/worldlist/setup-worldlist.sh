#!/bin/bash
# The worlds list on the hub server (run as root): a service on 127.0.0.1:54301 behind Caddy as
# https://hub.xiforever.com/worlds (Caddy gets the certificate). Run again any time to update it.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
id xifo-worldlist >/dev/null 2>&1 || useradd --system --home /var/lib/xifo-worldlist --shell /usr/sbin/nologin xifo-worldlist
mkdir -p /opt/xifo-worldlist /var/lib/xifo-worldlist
install -m 644 "$HERE/worldlist_service.py" /opt/xifo-worldlist/worldlist_service.py
chown xifo-worldlist:xifo-worldlist /var/lib/xifo-worldlist
chmod 700 /var/lib/xifo-worldlist
cat > /etc/systemd/system/xifo-worldlist.service <<'UNIT'
[Unit]
Description=XI: Forever Offline worlds list
After=network.target

[Service]
User=xifo-worldlist
ExecStart=/usr/bin/python3 /opt/xifo-worldlist/worldlist_service.py --port 54301 --data /var/lib/xifo-worldlist
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/xifo-worldlist
ProtectHome=true
PrivateTmp=true
MemoryMax=200M

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable xifo-worldlist >/dev/null 2>&1
systemctl restart xifo-worldlist
mkdir -p /etc/caddy/sites
cat > /etc/caddy/sites/hub-worldlist.caddy <<'SITE'
hub.xiforever.com {
	handle /worlds* {
		reverse_proxy 127.0.0.1:54301
	}
	respond 404
}
SITE
caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 || { rm -f /etc/caddy/sites/hub-worldlist.caddy; echo "Caddy refused the settings; the worlds list site was taken out again."; exit 1; }
systemctl reload caddy
sleep 3
echo "worlds list: $(systemctl is-active xifo-worldlist)"
curl -s http://127.0.0.1:54301/worlds/health; echo
curl -s --max-time 30 https://hub.xiforever.com/worlds/health; echo
