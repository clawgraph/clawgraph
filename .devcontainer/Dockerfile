FROM mcr.microsoft.com/devcontainers/python:3.11

# Install Node.js 22 (OpenClaw requires >=22)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install ClawGraph from source
WORKDIR /workspace
COPY . /workspace/
RUN pip install --no-cache-dir -e ".[dev]"

# Install OpenClaw globally (npm package is "openclaw")
RUN npm install -g openclaw@latest

# Create ClawGraph + OpenClaw config directories
RUN mkdir -p /root/.clawgraph /root/.openclaw/workspace/skills

# Default command
CMD ["bash"]
