#!/usr/bin/env bash
# Installs the OptiServe agent as a systemd service.
# Usage: sudo bash install.sh <BACKEND_URL> <AGENT_TOKEN> [REQUESTS_URL]
# One line: curl -fsSL <raw install.sh URL> | sudo bash -s -- https://optiserve.example.com osa_xxx
# Works on Amazon Linux 2023 and Ubuntu 22.04+. Override the agent source with OPTISERVE_AGENT_SRC.
set -euo pipefail

URL="${1:-}"
TOKEN="${2:-}"
REQUESTS_URL="${3:-}"
AGENT_SRC="${OPTISERVE_AGENT_SRC:-https://raw.githubusercontent.com/Vishwas-shettyy/OptiServe/v2/agent/optiserve_agent.py}"
PREFIX=/opt/optiserve-agent
ENV_FILE=/etc/optiserve-agent.env
UNIT=/etc/systemd/system/optiserve-agent.service

if [[ -z "$URL" || -z "$TOKEN" ]]; then
  echo "Usage: sudo bash install.sh <BACKEND_URL> <AGENT_TOKEN> [REQUESTS_URL]" >&2
  exit 1
fi
if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo)." >&2
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

echo "==> Installing the agent into $PREFIX"
mkdir -p "$PREFIX"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/optiserve_agent.py" ]]; then
  install -m 0755 "$SCRIPT_DIR/optiserve_agent.py" "$PREFIX/optiserve_agent.py"
else
  curl -fsSL "$AGENT_SRC" -o "$PREFIX/optiserve_agent.py"
  chmod 0755 "$PREFIX/optiserve_agent.py"
fi
python3 -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install -q --upgrade pip
"$PREFIX/venv/bin/pip" install -q "psutil>=5.9" "requests>=2.28"

echo "==> Writing $ENV_FILE (readable by root only)"
umask 077
cat > "$ENV_FILE" <<ENV
OPTISERVE_URL=$URL
OPTISERVE_TOKEN=$TOKEN
OPTISERVE_REQUESTS_URL=$REQUESTS_URL
ENV
chmod 600 "$ENV_FILE"
umask 022

echo "==> Writing $UNIT"
cat > "$UNIT" <<UNITFILE
[Unit]
Description=OptiServe metrics agent
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=$ENV_FILE
ExecStart=$PREFIX/venv/bin/python $PREFIX/optiserve_agent.py
Restart=always
RestartSec=5
DynamicUser=yes
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
UNITFILE

systemctl daemon-reload
systemctl enable --now optiserve-agent
systemctl restart optiserve-agent
sleep 2
systemctl --no-pager --lines=5 status optiserve-agent || true
echo "==> Done. Logs: journalctl -u optiserve-agent -f"
