FROM mcr.microsoft.com/devcontainers/python:3.11

# Install Node.js 22 (OpenClaw requires >=22)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install OpenClaw globally (npm package is "openclaw")
RUN npm install -g openclaw@latest

# Install Google Chrome (OpenClaw browser tool needs a real system browser)
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && dpkg -i google-chrome-stable_current_amd64.deb || true \
    && apt-get install -f -y \
    && rm google-chrome-stable_current_amd64.deb \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Playwright Chromium for browser-automation tasks (navigate/act/snapshot)
RUN npx playwright install --with-deps chromium

# Create ClawGraph + OpenClaw config directories
RUN mkdir -p /root/.clawgraph /root/.openclaw/workspace/skills

WORKDIR /workspace

# Default command
CMD ["bash"]
