#!/bin/sh
set -eu

PORT="${PORT:-80}"
TEMPLATE="/etc/nginx/templates/default.conf.template"
CONF="/etc/nginx/conf.d/default.conf"

# Substitute ${PORT} into nginx config (Render requires listening on $PORT)
sed "s/\${PORT}/${PORT}/g" "${TEMPLATE}" > "${CONF}"

exec nginx -g "daemon off;"
