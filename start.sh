#!/bin/bash
# Durable launcher for MoonshotHunt: Flask app + cloudflared tunnel under nohup.
cd /Users/neetipatel/moonshothunt || exit 1

pkill -f "app.py" 2>/dev/null
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 2

nohup .venv/bin/python app.py > /tmp/moonshot_app.log 2>&1 &
echo "app.py pid=$!"

# wait for Flask to be ready
for i in $(seq 1 20); do
  if curl -sS -m 3 -o /dev/null http://127.0.0.1:5001/health 2>/dev/null; then
    echo "flask ready"; break
  fi
  sleep 1
done

nohup cloudflared tunnel --url http://localhost:5001 > /tmp/moonshot_cf.log 2>&1 &
echo "cloudflared pid=$!"

# wait for the tunnel URL to appear in the log
for i in $(seq 1 30); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/moonshot_cf.log | head -1)
  [ -n "$URL" ] && break
  sleep 1
done
echo "TUNNEL_URL=$URL"
