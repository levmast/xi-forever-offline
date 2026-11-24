#!/usr/bin/env bash
# XI: Forever Offline - a world on a Linux server (a "cloud world", or the hub). What it does and its options: see
# usage() just below, or run it with --help.
set -euo pipefail

usage() {
  cat <<'USAGE'
XI: Forever Offline - a world on a Linux server (a "cloud world", or the hub).

  curl -fsSL https://<site>/install-world.sh | sudo bash
  curl -fsSL https://<site>/install-world.sh | sudo bash -s -- --name "My world" --yes
  sudo bash install-world.sh [options] [setup options]

What it does, on a fresh server (64-bit Intel/AMD, Ubuntu 22.04+ / Debian 12+ or any Linux from 2022 on with systemd):
  1. makes a user of its own for the world ("xifo"; the world never runs as root)
  2. downloads the Linux launcher of the newest full release into /opt/xifo-world and checks it against the release's
     checksum (no Python and no database have to be installed: both are inside)
  3. runs the world's setup: the game server, its database, and a few questions (name, who can come in, password,
     how many visitors, bots, rates)
  4. opens the game's ports in the server's own firewall, when one is switched on (ufw or firewalld)
  5. installs it as a service that starts at boot, is started again if it stops, saves its database every night and
     updates itself to every full release
Running it again on the same server keeps the world and its characters: it only asks the questions again.

Options of this script (everything else goes to the setup: --name, --address, --open / --friends, --password-file,
--max-guests, --world, --population, --rates, --bots, --yes):
  --dir DIR        where the world lives (default /opt/xifo-world; no spaces)
  --user NAME      the user it runs as (default xifo; made when missing)
  --service NAME   the service's name (default xifo-world)
  --kit-url URL    another download of the Linux launcher (default: the newest full release)
  --kit-file FILE  a launcher download that is already on this server (no checksum is fetched for it)
  --no-service     do not install a service: only set the world up and write run-world.sh, which runs it in the
                   foreground (and starts it again after an update)
  --no-firewall    leave the firewall alone
  --no-start       install the service but do not start it now
USAGE
}

main() {
  local dir="/opt/xifo-world" user="xifo" service="xifo-world" kit_url="" kit_file=""
  local with_service=1 with_firewall=1 start_now=1
  local release="https://github.com/Hurami89/xi-forever-offline/releases/latest/download"
  local package="XI-Forever-Offline-Linux.tar.gz" exe="XI-Forever-Offline"
  local -a setup_args=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --dir) dir="${2:?--dir needs a folder}"; shift 2 ;;
      --user) user="${2:?--user needs a name}"; shift 2 ;;
      --service) service="${2:?--service needs a name}"; shift 2 ;;
      --kit-url) kit_url="${2:?--kit-url needs a link}"; shift 2 ;;
      --kit-file) kit_file="${2:?--kit-file needs a file}"; shift 2 ;;
      --no-service) with_service=0; shift ;;
      --no-firewall) with_firewall=0; shift ;;
      --no-start) start_now=0; shift ;;
      -h|--help) usage; exit 0 ;;
      *) setup_args+=("$1"); shift ;;
    esac
  done

  say() { printf '%s\n' "$*"; }
  stop() { printf 'install-world: %s\n' "$*" >&2; exit 1; }

  # ----- can this server run a world? -----
  [ "$(uname -s)" = "Linux" ] || stop "this is for a Linux server."
  case "$(uname -m)" in
    x86_64|amd64) ;;
    *) stop "the game server is built for 64-bit Intel/AMD processors (x86-64); this machine is $(uname -m)." ;;
  esac
  [ "$(id -u)" -eq 0 ] || stop "run it as root (sudo bash install-world.sh): it makes a user and installs a service."
  case "$dir" in
    /*) ;;
    *) stop "--dir has to be a full path, like /opt/xifo-world." ;;
  esac
  case "$dir" in
    *[[:space:]]*) stop "--dir cannot have spaces in it (the database's own tools cannot take them)." ;;
    /|/usr|/usr/*|/etc|/etc/*|/boot|/boot/*|/bin|/sbin|/lib|/lib/*|/proc/*|/sys/*|/dev/*)
      stop "--dir cannot be a system folder. Use one of its own, like /opt/xifo-world or /srv/xifo-world." ;;
  esac
  [[ "$user" =~ ^[a-z_][a-z0-9_-]{0,30}$ ]] || stop "--user has to be a plain user name."
  [[ "$service" =~ ^[A-Za-z0-9_.-]+$ ]] || stop "--service has to be a plain name."
  if [ "$with_service" -eq 1 ] && ! command -v systemctl >/dev/null 2>&1; then
    stop "this server has no systemd. Use --no-service and start the world yourself with run-world.sh."
  fi
  local libc
  libc="$(ldd --version 2>/dev/null | head -n1 | grep -oE '[0-9]+\.[0-9]+$' || true)"
  if [ -n "$libc" ] && [ "$(printf '%s\n' "2.35" "$libc" | sort -V | head -n1)" != "2.35" ]; then
    stop "this Linux is too old (its C library is $libc; 2.35 or newer is needed: Ubuntu 22.04, Debian 12 or newer)."
  fi
  local tool
  for tool in tar gzip sha256sum; do
    command -v "$tool" >/dev/null 2>&1 || stop "'$tool' is missing on this server. Install it and run this again."
  done
  if [ -z "$kit_file" ] && ! command -v curl >/dev/null 2>&1; then
    stop "'curl' is missing on this server. Install it (apt-get install curl) and run this again."
  fi

  # ----- the user and the folder -----
  if ! id "$user" >/dev/null 2>&1; then
    say "Making the user '$user' for the world..."
    useradd --system --home-dir "$dir" --shell /usr/sbin/nologin "$user" 2>/dev/null \
      || useradd -r -d "$dir" -s /bin/false "$user" \
      || stop "the user '$user' could not be made."
  fi
  local group
  group="$(id -gn "$user")"
  mkdir -p "$dir"

  as_world() {                                   # runs a command as the world's user, in its folder
    if command -v runuser >/dev/null 2>&1; then
      (cd "$dir" && runuser -u "$user" -- "$@")
    else
      (cd "$dir" && sudo -u "$user" -- "$@")
    fi
  }

  # ----- the launcher -----
  local running=0
  if [ "$with_service" -eq 1 ] && systemctl is-active --quiet "$service" 2>/dev/null; then
    running=1
    say "The world is running: it is stopped for the setup (players get a minute to log out) and started again afterwards."
    systemctl stop "$service"
  fi
  if [ -x "$dir/$exe" ] && [ -z "$kit_url" ] && [ -z "$kit_file" ]; then
    say "The launcher is already in $dir (it updates itself); keeping it."
  else
    tmp="$(mktemp -d)"                           # (not local: the trap below runs after this function has ended)
    trap 'rm -rf "${tmp:-/nonexistent}"' EXIT
    if [ -n "$kit_file" ]; then
      [ -f "$kit_file" ] || stop "$kit_file is not there."
      cp "$kit_file" "$tmp/$package"
    else
      say "Downloading the launcher..."
      curl -fL --retry 3 -o "$tmp/$package" "${kit_url:-$release/$package}" \
        || stop "the download failed. (Right after a release the Linux files take about 40 minutes to appear: try again later.)"
      if [ -z "$kit_url" ]; then
        curl -fsSL --retry 3 -o "$tmp/sums.txt" "$release/SHA256SUMS-linux.txt" || stop "the release's checksums could not be downloaded."
        local want have
        want="$(awk -v n="$package" '$2 == n {print $1}' "$tmp/sums.txt" | head -n1)"
        have="$(sha256sum "$tmp/$package" | awk '{print $1}')"
        [ -n "$want" ] || stop "the release's checksums do not list $package."
        [ "$want" = "$have" ] || stop "the download does not match its published checksum. Nothing was installed."
        say "Checksum matches."
      fi
    fi
    tar -xzf "$tmp/$package" -C "$dir" --strip-components=1 --no-same-owner
    [ -f "$dir/$exe" ] || stop "that download is not the Linux launcher ($exe is not in it)."
    chmod 755 "$dir/$exe"
  fi
  [ -f "$dir/launcher_world.py" ] || stop "this launcher is from before worlds could run on a server. A newer release is needed."
  chown -R "$user:$group" "$dir"
  chmod 750 "$dir"

  # ----- the world's setup (asks its questions on the terminal) -----
  say "Setting up the world (the first time this downloads the game server and the database: a few minutes)..."
  if ! as_world "$dir/$exe" --run "$dir/launcher_world.py" setup ${setup_args[@]+"${setup_args[@]}"} </dev/null; then
    stop "the setup did not finish (see above). Nothing was started. Run this again when it is put right."
  fi

  # ----- the firewall on this server -----
  local port
  port="$(sed -n 's/.*"port": *\([0-9][0-9]*\).*/\1/p' "$dir/coop.json" 2>/dev/null | head -n1)"
  port="${port:-54100}"
  local tcp="54230 54231 54001 54002 51220 51240 $port" udp="54230" p
  if [ "$with_firewall" -eq 1 ]; then
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
      for p in $tcp; do ufw allow "$p/tcp" >/dev/null; done
      for p in $udp; do ufw allow "$p/udp" >/dev/null; done
      say "Firewall (ufw): opened TCP $tcp and UDP $udp."
    elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
      for p in $tcp; do firewall-cmd --quiet --permanent --add-port="$p/tcp"; done
      for p in $udp; do firewall-cmd --quiet --permanent --add-port="$p/udp"; done
      firewall-cmd --quiet --reload
      say "Firewall (firewalld): opened TCP $tcp and UDP $udp."
    else
      say "No firewall is switched on on this server itself."
    fi
  fi
  say "If your host has a firewall in its control panel, open there too: TCP $tcp and UDP $udp."

  # ----- running it -----
  cat > "$dir/run-world.sh" <<RUN
#!/bin/sh
# Runs this world in the foreground (Ctrl+C stops it) and starts it again after it updated itself.
cd "$dir" || exit 1
while :; do
  "$dir/$exe" --run "$dir/launcher_world.py" run
  code=\$?
  [ "\$code" -eq 75 ] || exit "\$code"
done
RUN
  chmod 755 "$dir/run-world.sh"
  chown "$user:$group" "$dir/run-world.sh"

  if [ "$with_service" -eq 0 ]; then
    say ""
    say "The world is set up in $dir. Start it as '$user':"
    say "  sudo -u $user $dir/run-world.sh"
    return 0
  fi

  cat > "/etc/systemd/system/$service.service" <<UNIT
[Unit]
Description=XI: Forever Offline world ($dir)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$user
Group=$group
WorkingDirectory=$dir
ExecStart=$dir/$exe --run $dir/launcher_world.py run
# 75: it stopped to update itself and wants to be started again. 78: a person has to look first (see its status).
Restart=always
RestartSec=10
SuccessExitStatus=75
RestartPreventExitStatus=78
# Stopping: only the world's own program is told (it warns the players, gives them a minute, then stops the game
# servers and the database in the right order). Whatever is left after four minutes is ended.
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=240
LimitNOFILE=65536
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=false

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable "$service" >/dev/null 2>&1 || true
  rm -f "$dir/logs/world-status.json"            # (what an earlier run last wrote: the wait below reads the new one)
  if [ "$start_now" -eq 0 ]; then
    say ""
    say "The service '$service' is installed but not started.   sudo systemctl start $service"
    return 0
  fi
  if [ "$running" -eq 1 ]; then
    systemctl restart "$service"
  else
    systemctl start "$service"
  fi

  say "Starting the world (the first start loads everything: a minute or two)..."
  local waited=0 state=""
  while [ "$waited" -lt 600 ]; do
    sleep 5
    waited=$((waited + 5))
    state="$(sed -n 's/.*"state": *"\([a-z]*\)".*/\1/p' "$dir/logs/world-status.json" 2>/dev/null | head -n1)"
    [ "$state" = "running" ] && break
    if ! systemctl is-active --quiet "$service"; then
      state="failed"
      break
    fi
  done
  say ""
  if [ "$state" = "running" ]; then
    as_world "$dir/$exe" --run "$dir/launcher_world.py" status </dev/null || true
    say ""
    say "The world is up. It starts by itself when the server boots."
  else
    say "The world is not up yet (state: ${state:-unknown}). Its own account of what happened:"
    tail -n 25 "$dir/logs/world.log" 2>/dev/null || true
  fi
  say ""
  say "  sudo systemctl status $service        is it running"
  say "  sudo systemctl stop $service          stop it (players get a minute)      start: sudo systemctl start $service"
  say "  sudo -u $user $dir/$exe --run $dir/launcher_world.py status     visitors, the world's link, backups, updates"
  say "  $dir/logs/world.log                   what the world did"
  say "  $dir/backups/world/                   the nightly copies of its database"
}

main "$@"
