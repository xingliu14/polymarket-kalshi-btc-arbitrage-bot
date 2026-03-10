#!/bin/bash
# Usage: ./deploy.sh
# Deploys latest code to VPS and restarts services.

set -e

SERVER="root@89.167.72.63"
REMOTE_DIR="/opt/arbitrage-bot"
LOCAL_DIR="$(dirname "$0")"

echo "==> Syncing files..."
rsync -az --delete \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='backend/venv' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/.next' \
  --exclude='backend/.env' \
  --exclude='frontend/.env.local' \
  "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

echo "==> Installing backend dependencies..."
ssh "$SERVER" "cd $REMOTE_DIR/backend && source venv/bin/activate && pip install -r requirements.txt -q"

echo "==> Building frontend..."
ssh "$SERVER" "cd $REMOTE_DIR/frontend && npm install --silent && npm run build"

echo "==> Restarting services..."
ssh "$SERVER" "systemctl restart arbitrage-backend arbitrage-frontend"

echo "==> Done! http://89.167.72.63:3000"
