#!/usr/bin/env bash
set -euo pipefail

GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-lobstergym-dev-token}"

echo '=== Setting up OpenClaw with ClawGraph skill ==='
echo "Chrome: $(google-chrome-stable --version 2>&1 || echo 'NOT FOUND')"

mkdir -p /root/.openclaw/workspace/skills

python - <<'PY'
import json
import os
import shutil
from datetime import date
from pathlib import Path

src = Path("/workspace/skills/clawgraph")
dst = Path("/root/.openclaw/workspace/skills/clawgraph")
clawgraph_config_path = Path("/root/.clawgraph/config.yaml")
workspace_memory_path = Path("/root/.openclaw/workspace/MEMORY.md")
workspace_user_path = Path("/root/.openclaw/workspace/USER.md")
workspace_daily_memory_dir = Path("/root/.openclaw/workspace/memory")
workspace_daily_memory_path = workspace_daily_memory_dir / f"{date.today().isoformat()}.md"
workspace_previous_daily_memory_path = workspace_daily_memory_dir / f"{date.fromordinal(date.today().toordinal() - 1).isoformat()}.md"

workspace_memory_policy = (
    "# Workspace Memory Policy\n\n"
    "- ClawGraph is the durable memory system for this workspace.\n"
    "- Always use the clawgraph skill immediately when the user shares durable facts worth remembering.\n"
    "- Do not store durable user facts in MEMORY.md or daily markdown memory files.\n"
    "- Never rely on chat context or markdown memory files as a substitute for ClawGraph.\n"
    "- Do not claim you stored or remembered durable facts unless you actually used ClawGraph successfully.\n"
    "- Use markdown memory files only for temporary workspace notes that do not belong in long-term user memory.\n"
)

if dst.exists():
    shutil.rmtree(dst)

shutil.copytree(src, dst)

clawgraph_config_path.parent.mkdir(parents=True, exist_ok=True)
clawgraph_config_path.write_text(
    "llm:\n"
    "  model: gpt-5.4-mini\n"
    "  temperature: 0.0\n",
    encoding="utf-8",
)

workspace_memory_path.parent.mkdir(parents=True, exist_ok=True)
workspace_memory_path.write_text(workspace_memory_policy, encoding="utf-8")
workspace_user_path.write_text(workspace_memory_policy, encoding="utf-8")
workspace_daily_memory_dir.mkdir(parents=True, exist_ok=True)
workspace_daily_memory_path.write_text(workspace_memory_policy, encoding="utf-8")
workspace_previous_daily_memory_path.write_text(workspace_memory_policy, encoding="utf-8")

config = {
    "gateway": {
        "mode": "local",
        "bind": "lan",
        "auth": {
            "mode": "token",
            "token": os.environ.get("OPENCLAW_GATEWAY_TOKEN", "lobstergym-dev-token"),
        },
        "controlUi": {
            "enabled": True,
            "dangerouslyDisableDeviceAuth": True,
            "allowInsecureAuth": True,
            "allowedOrigins": [
                "http://localhost:18789",
                "http://127.0.0.1:18789",
            ],
        },
    },
    "agents": {
        "defaults": {
            "model": {
                "primary": "openai/gpt-5.4",
            }
        }
    },
    "channels": {
        "whatsapp": {
            "dmPolicy": "open",
            "allowFrom": ["*"],
        }
    },
    "browser": {
        "enabled": True,
        "headless": True,
        "noSandbox": True,
        "executablePath": "/usr/bin/google-chrome-stable",
        "ssrfPolicy": {
            "dangerouslyAllowPrivateNetwork": True,
        },
    },
}

Path("/root/.openclaw/openclaw.json").write_text(
    json.dumps(config, indent=2),
    encoding="utf-8",
)
PY

pip install -e /workspace

echo '=== Available skills ==='
openclaw skills list --json || true

echo '=== Starting OpenClaw gateway on port 18789 ==='
echo "WebChat/Control UI: http://127.0.0.1:18789/?token=${GATEWAY_TOKEN}"

exec openclaw gateway run --bind lan --port 18789 --token "${GATEWAY_TOKEN}" --verbose