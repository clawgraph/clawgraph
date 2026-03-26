#!/bin/bash
# Debug script: run a single eval task against external gateway
OUT=/workspace/lobstergym/reports/debug-output.txt
> $OUT

echo "=== Setup ===" >> $OUT
pip install -e /workspace >/dev/null 2>&1 || true
pip install requests >/dev/null 2>&1 || true

# Write minimal client config if none exists
if [ ! -f /root/.openclaw/openclaw.json ]; then
  mkdir -p /root/.openclaw
  cat > /root/.openclaw/openclaw.json << CONF
  {
    "gateway": {
      "auth": {
        "mode": "token",
        "token": "${OPENCLAW_GATEWAY_TOKEN:-lobstergym-dev-token}"
      }
    }
  }
CONF
fi

# Resolve gateway hostname to IP for OpenClaw's private-WS security check
if [ -n "${OPENCLAW_GATEWAY_HOST}" ] && [ -z "${OPENCLAW_GATEWAY_URL}" ]; then
  GATEWAY_IP=$(getent hosts "${OPENCLAW_GATEWAY_HOST}" | awk '{print $1}')
  export OPENCLAW_GATEWAY_URL="ws://${GATEWAY_IP}:18789"
fi

echo "Gateway URL: ${OPENCLAW_GATEWAY_URL:-not set}" >> $OUT

echo "" >> $OUT
TASK="${1:-api-weather-check}"
echo "=== Single eval task ($TASK) ===" >> $OUT
LOBSTERGYM_WEB_BASE=http://lobstergym-web:8080 LOBSTERGYM_API_BASE=http://lobstergym-api:8090 LOBSTERGYM_DEBUG=1 \
  timeout 180 python -m lobstergym.eval.runner --profile clawgraph --task "$TASK" --output /tmp/eval-test.json >> $OUT 2>&1
echo "eval exit=$?" >> $OUT
echo "" >> $OUT
echo "=== Eval report ===" >> $OUT
python -c "import json; r=json.load(open('/tmp/eval-test.json')); print(json.dumps(r, indent=2)[:2000])" >> $OUT 2>&1

echo "=== DONE ===" >> $OUT
