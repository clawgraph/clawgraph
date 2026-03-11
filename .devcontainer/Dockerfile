FROM mcr.microsoft.com/devcontainers/python:3.11

# Install Node.js 22 (OpenClaw requires >=22)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install OpenClaw globally (npm package is "openclaw")
RUN npm install -g openclaw@latest

# Install Playwright Chromium for browser-automation tasks
RUN npx playwright install --with-deps chromium

# Create ClawGraph + OpenClaw config directories
RUN mkdir -p /root/.clawgraph /root/.openclaw/workspace/skills

WORKDIR /workspace

# Default command
CMD ["bash"]
