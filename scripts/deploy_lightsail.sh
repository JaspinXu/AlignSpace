#!/usr/bin/env bash
# Deploy the committed HEAD to the organiser-provided Lightsail instance.
#
#   scripts/deploy_lightsail.sh ubuntu@<PUBLIC_IP> ~/.ssh/alignspace-lightsail.pem [--https|--http]
#
# Before the first run, open TCP 80 and 443 in the Lightsail console (Networking > IPv4 firewall).
# The first run creates /home/ubuntu/alignspace/shared/.env from .env.example: edit it on the
# instance (LLM gateway URL, model, key) and run the script again. Later runs keep .env and data.
# Only committed files are shipped (git archive), so local databases, uploads and secrets never leave.
set -euo pipefail

TARGET="${1:?usage: deploy_lightsail.sh ubuntu@IP key.pem [--https|--http]}"
KEY="${2:?path to the Lightsail private key}"
MODE="${3:---https}"
HOST="${TARGET#*@}"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$TARGET")
REV="$(git rev-parse --short HEAD)"
ARCHIVE="$(mktemp -t alignspace-XXXX).tar.gz"

git diff --quiet HEAD -- || echo "warning: uncommitted changes are NOT deployed (shipping $REV)"
git archive --format=tar.gz -o "$ARCHIVE" HEAD
scp -i "$KEY" -o StrictHostKeyChecking=accept-new "$ARCHIVE" "$TARGET:/tmp/alignspace-$REV.tar.gz"
rm -f "$ARCHIVE"

if [[ "$MODE" == "--https" ]]; then SITE="${HOST}.sslip.io"; SECURE=true; else SITE=":80"; SECURE=false; fi

"${SSH[@]}" "REV=$REV SITE='$SITE' SECURE=$SECURE bash -s" <<'REMOTE'
set -euo pipefail
ROOT=/home/ubuntu/alignspace
mkdir -p "$ROOT/releases/$REV" "$ROOT/shared/data/uploads"
tar -xzf "/tmp/alignspace-$REV.tar.gz" -C "$ROOT/releases/$REV" && rm -f "/tmp/alignspace-$REV.tar.gz"
if ! command -v python3 >/dev/null || ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
  sudo apt-get update -y && sudo apt-get install -y python3 python3-venv
fi
python3 -m venv "$ROOT/releases/$REV/.venv"
"$ROOT/releases/$REV/.venv/bin/pip" install -q --timeout 60 --retries 5 -r "$ROOT/releases/$REV/requirements.txt"
FIRST_ENV=false
if [[ ! -f "$ROOT/shared/.env" ]]; then
  cp "$ROOT/releases/$REV/.env.example" "$ROOT/shared/.env"; chmod 600 "$ROOT/shared/.env"; FIRST_ENV=true
fi
grep -q '^ALIGNSPACE_SECURE_COOKIES=' "$ROOT/shared/.env" \
  && sed -i "s/^ALIGNSPACE_SECURE_COOKIES=.*/ALIGNSPACE_SECURE_COOKIES=$SECURE/" "$ROOT/shared/.env" \
  || echo "ALIGNSPACE_SECURE_COOKIES=$SECURE" >> "$ROOT/shared/.env"
PREVIOUS="$(readlink -f "$ROOT/current" 2>/dev/null || true)"
ln -sfn "$ROOT/releases/$REV" "$ROOT/current"
sudo cp "$ROOT/current/deploy/alignspace.service" /etc/systemd/system/alignspace.service
sudo systemctl daemon-reload && sudo systemctl enable -q alignspace && sudo systemctl restart alignspace
if ! command -v caddy >/dev/null; then
  sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y && sudo apt-get install -y caddy
fi
sudo cp "$ROOT/current/deploy/Caddyfile" /etc/caddy/Caddyfile
sudo mkdir -p /etc/systemd/system/caddy.service.d
printf '[Service]\nEnvironment=SITE_ADDRESS=%s\n' "$SITE" | sudo tee /etc/systemd/system/caddy.service.d/site.conf >/dev/null
sudo systemctl daemon-reload && sudo systemctl restart caddy
for i in $(seq 1 20); do curl -fs http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
if ! curl -fs http://127.0.0.1:8010/health; then
  echo "health check failed; rolling back to ${PREVIOUS:-nothing}"
  [[ -n "$PREVIOUS" ]] && ln -sfn "$PREVIOUS" "$ROOT/current" && sudo systemctl restart alignspace
  exit 1
fi
echo; echo "deployed $REV"
ls -1dt "$ROOT"/releases/* | tail -n +4 | xargs -r rm -rf   # keep the three newest releases
$FIRST_ENV && echo "FIRST RUN: edit $ROOT/shared/.env (gateway URL, model, key), then: sudo systemctl restart alignspace"
REMOTE

if [[ "$MODE" == "--https" ]]; then URL="https://${HOST}.sslip.io"; else URL="http://${HOST}"; fi
echo "Public URL: $URL   (check it from a signed-out/private browser window)"
curl -fsS --max-time 20 "$URL/health" && echo || echo "Public check failed: confirm ports 80/443 are open in the Lightsail firewall."
