#!/bin/bash
# The armory on the hub server (run as root): character pages on xiforever.com (/c/<Name>, /armory, /armory/fame),
# the phone app's pairing and portable fishing, and the app itself at xiforever.com/app (kept on the newest release of
# Hurami89/xifo-app by itself: update_app_web.py every 10 minutes). Installs the service on 127.0.0.1:54302 (user xifo-armory, starts at
# boot) and adds two routes to the xiforever.com site in Caddy. Run again any time to update it; the data in
# /var/lib/xifo-armory stays.
#
# Caddy: the xiforever.com site file gets one line, "import /etc/caddy/xifo-armory.inc" (marked "# xifo-armory").
# If the website's own setup (setup-web.sh) writes that site file again later, run this script again to put it back.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
id xifo-armory >/dev/null 2>&1 || useradd --system --home /var/lib/xifo-armory --shell /usr/sbin/nologin xifo-armory
mkdir -p /opt/xifo-armory /var/lib/xifo-armory
install -m 644 "$HERE/armory_service.py" /opt/xifo-armory/armory_service.py
install -m 644 "$HERE/update_app_web.py" /opt/xifo-armory/update_app_web.py
# (2026-11-25) Ventures: the simulation and the camps built from the server's data (dev/ventures/build_venture_data.py)
install -m 644 "$HERE/ventures.py" /opt/xifo-armory/ventures.py
install -m 644 "$HERE/ventures_hub.py" /opt/xifo-armory/ventures_hub.py
install -m 644 "$HERE/tetra_rules.py" /opt/xifo-armory/tetra_rules.py      # (2026-11-25) Tetra Master PvP
install -m 644 "$HERE/tetra_hub.py" /opt/xifo-armory/tetra_hub.py
install -m 644 "$HERE/tetra_cards.json" /opt/xifo-armory/tetra_cards.json
install -m 644 "$HERE/venture_data.json" /opt/xifo-armory/venture_data.json
mkdir -p /var/lib/xifo-app-web/releases
chown -R xifo-armory:xifo-armory /var/lib/xifo-app-web
chmod 755 /var/lib/xifo-app-web /var/lib/xifo-app-web/releases
rm -rf /opt/xifo-armory/static
cp -r "$HERE/static" /opt/xifo-armory/static
chmod -R a+rX /opt/xifo-armory
chown -R xifo-armory:xifo-armory /var/lib/xifo-armory
chmod 750 /var/lib/xifo-armory

cat > /etc/systemd/system/xifo-armory.service <<'UNIT'
[Unit]
Description=XI: Forever Offline armory (character pages, phone app)
After=network.target

[Service]
User=xifo-armory
Group=xifo-armory
ExecStart=/usr/bin/python3 /opt/xifo-armory/armory_service.py --port 54302 --data /var/lib/xifo-armory --static /opt/xifo-armory/static
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/xifo-armory
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/xifo-app-web.service <<'UNIT'
[Unit]
Description=Keep xiforever.com/app on the newest XIFO app release
After=network-online.target

[Service]
Type=oneshot
User=xifo-armory
Group=xifo-armory
ExecStart=/usr/bin/python3 /opt/xifo-armory/update_app_web.py --data /var/lib/xifo-app-web
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/xifo-app-web
PrivateTmp=true
UNIT
cat > /etc/systemd/system/xifo-app-web.timer <<'UNIT'
[Unit]
Description=Check for a new XIFO app release every 10 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=10min
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable xifo-armory >/dev/null 2>&1
systemctl restart xifo-armory
systemctl enable --now xifo-app-web.timer >/dev/null 2>&1
systemctl start xifo-app-web.service || true

cat > /etc/caddy/xifo-armory.inc <<'INC'
handle /c/* {
	reverse_proxy 127.0.0.1:54302
}
handle /armory* {
	reverse_proxy 127.0.0.1:54302
}
redir /app /app/ 308
handle_path /app/* {
	root * /var/lib/xifo-app-web/current
	@page not path /_expo/* /assets/*
	header @page Cache-Control "no-cache"
	header /_expo/* Cache-Control "public, max-age=31536000, immutable"
	try_files {path} /index.html
	file_server
}
INC

SITE=$(grep -lE '^\s*(https?://)?xiforever\.com(:[0-9]+)?\s*(,[^{]*)?\{' /etc/caddy/sites/*.caddy /etc/caddy/Caddyfile 2>/dev/null | head -1 || true)
if [ -z "$SITE" ]; then
	echo "Could not find the xiforever.com site in Caddy (/etc/caddy/sites/*.caddy). Is the website set up on this server?"
	echo "The armory itself runs ($(systemctl is-active xifo-armory)) at 127.0.0.1:54302, but the site does not show it yet."
	exit 1
fi
if ! grep -q "xifo-armory.inc" "$SITE"; then
	cp "$SITE" "$SITE.before-armory"
	# the line goes right after the site's opening "xiforever.com {" line
	awk 'done==0 && /^[[:space:]]*(https?:\/\/)?xiforever\.com(:[0-9]+)?[[:space:]]*(,[^{]*)?\{/ {print; print "\timport /etc/caddy/xifo-armory.inc  # xifo-armory"; done=1; next} {print}' \
		"$SITE.before-armory" > "$SITE"
fi
if ! caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
	[ -f "$SITE.before-armory" ] && cp "$SITE.before-armory" "$SITE"
	echo "Caddy refused the settings; the site file was put back as it was. The armory is not on the site yet."
	exit 1
fi
systemctl reload caddy
sleep 2
echo "armory: $(systemctl is-active xifo-armory)  (site file: $SITE)"
curl -s http://127.0.0.1:54302/armory/health; echo
curl -s --max-time 30 https://xiforever.com/armory/health; echo
journalctl -u xifo-app-web.service -n 3 --no-pager -o cat 2>/dev/null || true
