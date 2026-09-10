#!/bin/bash
set -e

echo "[STARTUP] Starting bgutil POT server on localhost:4416..."
cd /app/pot_server/bgutil/server && npm start > /app/bgutil.log 2>&1 &
cd /app

# Wait for bgutil to start
sleep 2

echo "[STARTUP] Starting Cloudflare Tunnel..."
cloudflared tunnel run --url http://127.0.0.1:8000 ytsong-api > cloudflared.log 2>&1 &

echo "[STARTUP] Starting Syntiox DL API (uvicorn)..."
exec uvicorn app:app --host 0.0.0.0 --port 8000
