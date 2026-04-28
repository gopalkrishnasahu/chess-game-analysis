#!/usr/bin/env bash
# Deploy the chess-game-analysis app on the Linode server.
# Run this on the Linode server (not locally).
# Assumes Stockfish is already installed (stockfish.sh already ran).
#
# Usage:
#   chmod +x deploy_linode.sh
#   ./deploy_linode.sh

set -e

REPO_URL="https://github.com/gopalkrishnasahu/chess-game-analysis.git"
APP_DIR="$HOME/chess-game-analysis"
SERVICE_USER="$(whoami)"
STOCKFISH_BIN=$(which stockfish)
PORT=5000

echo "=== Cloning repo ==="
if [ -d "$APP_DIR/.git" ]; then
    echo "Repo already exists — pulling latest..."
    git -C "$APP_DIR" pull origin main
else
    git clone "$REPO_URL" "$APP_DIR"
fi

echo ""
echo "=== Setting up Python environment ==="
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo ""
echo "=== Creating .env ==="
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" << EOF
STOCKFISH_PATH=$STOCKFISH_BIN
EOF
    echo ".env created"
else
    # Make sure STOCKFISH_PATH is set
    if ! grep -q "STOCKFISH_PATH" "$APP_DIR/.env"; then
        echo "STOCKFISH_PATH=$STOCKFISH_BIN" >> "$APP_DIR/.env"
        echo "Added STOCKFISH_PATH to existing .env"
    else
        echo ".env already exists — skipped (edit manually if needed)"
    fi
fi

echo ""
echo "=== Creating systemd service ==="
sudo tee /etc/systemd/system/chess-app.service > /dev/null << EOF
[Unit]
Description=Chess Game Analysis (gunicorn)
After=network.target

[Service]
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn \\
    --workers 1 --threads 4 --timeout 300 \\
    --bind 127.0.0.1:$PORT \\
    app:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable chess-app
sudo systemctl restart chess-app
sleep 2
sudo systemctl status chess-app --no-pager

echo ""
echo "=== Configuring nginx ==="
sudo tee /etc/nginx/conf.d/chess-app.conf > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # Required for SSE live progress bar
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header X-Accel-Buffering no;

        proxy_read_timeout 310s;
        proxy_send_timeout 310s;
    }
}
EOF

sudo nginx -t
sudo systemctl reload nginx

echo ""
echo "=== Done! ==="
PUBLIC_IP=$(curl -s ifconfig.me || hostname -I | awk '{print $1}')
echo ""
echo "Chess app is live at: http://$PUBLIC_IP"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status chess-app      # check service"
echo "  sudo journalctl -u chess-app -f      # live logs"
echo "  git -C $APP_DIR pull && sudo systemctl restart chess-app  # update app"
