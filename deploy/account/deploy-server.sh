#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=/opt/trainer-account
install -d -m 0750 "$APP_ROOT/app" "$APP_ROOT/data"
id trainer-account >/dev/null 2>&1 || useradd --system --home "$APP_ROOT" --shell /usr/sbin/nologin trainer-account
chown -R trainer-account:trainer-account "$APP_ROOT"
tar -xzf /tmp/trainer-account-service.tar.gz -C "$APP_ROOT/app"
chown -R trainer-account:trainer-account "$APP_ROOT/app"
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get update
apt-get install -y python3-venv python3-pip
test -x "$APP_ROOT/venv/bin/python" || python3 -m venv "$APP_ROOT/venv"
"$APP_ROOT/venv/bin/pip" install --upgrade pip gunicorn==23.0.0
install -m 0644 /tmp/trainer-account.service /etc/systemd/system/trainer-account.service
install -m 0644 /tmp/nginx-rate-limit.conf /etc/nginx/conf.d/trainer-account-rate-limit.conf
# Keep the rollback copy outside sites-enabled.  A backup inside that directory
# is parsed as another virtual-host file and makes repeated deploys fail with a
# duplicate :443 listener.
cp -a /etc/nginx/sites-enabled/tiny-board /etc/nginx/tiny-board.before-trainer-account
python3 - <<'PY'
from pathlib import Path
site = Path('/etc/nginx/sites-enabled/tiny-board')
snippet = Path('/tmp/nginx-location.conf').read_text()
text = site.read_text()
marker = '    location / {'
if 'location ^~ /trainer-account/' not in text:
    first = text.find(marker)
    if first < 0:
        raise SystemExit('Nginx site layout changed; backup retained and no change made')
    text = text[:first] + snippet + '\n' + text[first:]
    site.write_text(text)
PY
nginx -t
systemctl daemon-reload
systemctl enable --now trainer-account
systemctl reload nginx
status=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 10 http://127.0.0.1:8788/v1/session -X POST -H 'Content-Type: application/json' -d '{}')
test "$status" = 400
