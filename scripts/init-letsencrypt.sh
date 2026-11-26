#!/bin/sh
# One-time: obtain the first real certificate. Run on the server after DNS for $DOMAIN points at it and ports 80/443 are open.
set -eu
set -a; . ./.env.production; set +a
: "${DOMAIN:?}"
[ -n "${LE_EMAIL:-}" ] || { echo "export LE_EMAIL=you@example.com first" >&2; exit 1; }
docker compose --env-file .env.production -f docker-compose.prod.yml up -d nginx
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" --email "$LE_EMAIL" --agree-tos --no-eff-email --force-renewal
docker compose --env-file .env.production -f docker-compose.prod.yml exec nginx nginx -s reload
echo "Certificate issued for $DOMAIN"
