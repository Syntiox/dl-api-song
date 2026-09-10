#!/bin/bash
set -e

echo "[STARTUP] Starting Cloudflare Tunnel..."
cloudflared tunnel run --url http://127.0.0.1:8000 ytsong-api > cloudflared.log 2>&1 &

echo "[STARTUP] Starting Syntiox DL API (uvicorn)..."
exec /home/shalu/Downloads/DL-API-1/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
