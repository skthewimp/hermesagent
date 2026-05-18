#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HERMES_ENV_FILE:-$HOME/.hermes/.env}"

mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE" || true

printf "Gmail address for Hermes SMTP/IMAP: "
read -r EMAIL_ADDRESS
if [[ -z "${EMAIL_ADDRESS// }" ]]; then
  echo "Email address is required." >&2
  exit 1
fi

printf "Allowed sender email [default: %s]: " "$EMAIL_ADDRESS"
read -r EMAIL_ALLOWED_USERS
EMAIL_ALLOWED_USERS="${EMAIL_ALLOWED_USERS:-$EMAIL_ADDRESS}"

printf "Home delivery email [default: %s]: " "$EMAIL_ADDRESS"
read -r EMAIL_HOME_ADDRESS
EMAIL_HOME_ADDRESS="${EMAIL_HOME_ADDRESS:-$EMAIL_ADDRESS}"

printf "Gmail app password (input hidden): "
read -rs EMAIL_PASSWORD
printf "\n"
if [[ -z "${EMAIL_PASSWORD// }" ]]; then
  echo "App password is required." >&2
  exit 1
fi

python3 - "$ENV_FILE" "$EMAIL_ADDRESS" "$EMAIL_PASSWORD" "$EMAIL_ALLOWED_USERS" "$EMAIL_HOME_ADDRESS" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1]).expanduser()
updates = {
    "EMAIL_ADDRESS": sys.argv[2],
    "EMAIL_PASSWORD": sys.argv[3],
    "EMAIL_IMAP_HOST": "imap.gmail.com",
    "EMAIL_IMAP_PORT": "993",
    "EMAIL_SMTP_HOST": "smtp.gmail.com",
    "EMAIL_SMTP_PORT": "587",
    "EMAIL_POLL_INTERVAL": "15",
    "EMAIL_ALLOWED_USERS": sys.argv[4],
    "EMAIL_HOME_ADDRESS": sys.argv[5],
}

lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
seen = set()
out = []
for line in lines:
    stripped = line.lstrip()
    commented = stripped.startswith("#")
    body = stripped[1:].lstrip() if commented else stripped
    if "=" in body:
        key = body.split("=", 1)[0].strip()
        if key in updates:
            if key not in seen:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
            continue
    out.append(line)

if out and out[-1].strip():
    out.append("")
out.append("# Email (IMAP/SMTP) configured by scripts/configure_gmail_email.sh")
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")

env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

chmod 600 "$ENV_FILE" || true
echo "Configured Gmail email settings in $ENV_FILE"
echo "Restart Hermes with: pm2 restart hermes --update-env"
