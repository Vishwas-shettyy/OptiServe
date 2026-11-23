#!/usr/bin/env bash
# Installs the OptiServe demo app as a systemd service (port 80 by default).
# Usage: sudo bash install.sh [PORT]
# Works on Amazon Linux 2023 and Ubuntu 22.04+. Override the app source with DEMO_APP_SRC (a URL to app.py).
set -euo pipefail

PORT="${1:-80}"
APP_SRC="${DEMO_APP_SRC:-https://raw.githubusercontent.com/Vishwas-shettyy/OptiServe/v2/demo/demo_app/app.py}"
PREFIX=/opt/optiserve-demo-app
UNIT=/etc/systemd/system/optiserve-demo-app.service

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo)." >&2
  exit 1
fi
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "PORT must be a number between 1 and 65535." >&2
  exit 1
fi

echo "==> Installing Python"
if command -v apt-get >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get update -y -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3 python3-venv curl
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y -q python3 python3-pip
elif command -v yum >/dev/null 2>&1; then
  yum install -y -q python3 python3-pip
else
  echo "Unsupported OS: need apt-get, dnf or yum." >&2
  exit 1
fi

echo "==> Installing the demo app into $PREFIX"
mkdir -p "$PREFIX"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/app.py" ]]; then
  install -m 0644 "$SCRIPT_DIR/app.py" "$PREFIX/app.py"
  REQS="$SCRIPT_DIR/requirements.txt"
else
  curl -fsSL "$APP_SRC" -o "$PREFIX/app.py"
  REQS=""
fi
python3 -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install -q --upgrade pip
if [[ -n "$REQS" && -f "$REQS" ]]; then
  "$PREFIX/venv/bin/pip" install -q -r "$REQS"
else
  "$PREFIX/venv/bin/pip" install -q "fastapi>=0.100" "uvicorn[standard]>=0.23"
fi

echo "==> Writing $UNIT"
cat > "$UNIT" <<UNITFILE
[Unit]
Description=OptiServe demo app (real CPU work per request)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$PREFIX
ExecStart=$PREFIX/venv/bin/uvicorn app:app --host 0.0.0.0 --port $PORT --no-access-log
Restart=always
RestartSec=3
DynamicUser=yes
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
UNITFILE

systemctl daemon-reload
systemctl enable --now optiserve-demo-app
systemctl restart optiserve-demo-app

echo "==> Waiting for the app on port $PORT"
for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$PORT/metrics" >/dev/null 2>&1; then
    echo "==> Done. http://127.0.0.1:$PORT/  ·  counter: http://127.0.0.1:$PORT/metrics"
    echo "    Logs: journalctl -u optiserve-demo-app -f"
    exit 0
  fi
  sleep 1
done
echo "The app did not answer yet. Check: journalctl -u optiserve-demo-app -n 50" >&2
exit 1
