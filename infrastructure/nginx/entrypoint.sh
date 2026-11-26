#!/bin/sh
# Substitutes ${DOMAIN} (only) into the config, then runs nginx. Starts with a throwaway self-signed cert if Let's Encrypt has not issued one yet.
set -eu
: "${DOMAIN:?DOMAIN is required}"
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
if [ ! -f "$CERT_DIR/fullchain.pem" ]; then
  echo "No certificate for $DOMAIN yet: creating a temporary self-signed one so nginx can start (run scripts/init-letsencrypt.sh)"
  mkdir -p "$CERT_DIR"
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 -keyout "$CERT_DIR/privkey.pem" -out "$CERT_DIR/fullchain.pem" -subj "/CN=$DOMAIN" 2>/dev/null
fi
envsubst '${DOMAIN}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf
# reload every 6h so renewed certificates are picked up
( while :; do sleep 6h; nginx -s reload 2>/dev/null || true; done ) &
exec nginx -g 'daemon off;'
