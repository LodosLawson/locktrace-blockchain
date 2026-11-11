#!/bin/bash
# ==============================================================================
# SEC-NET-01: Secure Netlify Deployment Wrapper
# DO NOT hardcode sensitive Netlify auth tokens or JWE proxy paths in this script.
# Provide NETLIFY_PROXY_PATH or NETLIFY_AUTH_TOKEN via environment variables or CI/CD secrets.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"

if [ -d "$FRONTEND_DIR" ]; then
    cd "$FRONTEND_DIR"
elif [ -d "/opt/blockchaint/frontend" ]; then
    cd "/opt/blockchaint/frontend"
fi

SITE_ID="${NETLIFY_SITE_ID:-b987ae8a-de6e-48cc-b75e-535dcdc5e31d}"
PROXY_PATH="${NETLIFY_PROXY_PATH:-}"

if [ -n "$PROXY_PATH" ]; then
    npx -y @netlify/mcp@latest --site-id "$SITE_ID" --proxy-path "$PROXY_PATH" --no-wait
else
    # Safe production deploy using official Netlify CLI
    echo "[INFO] NETLIFY_PROXY_PATH not set; deploying via netlify-cli..."
    npx -y netlify-cli deploy --prod --dir=.
fi
