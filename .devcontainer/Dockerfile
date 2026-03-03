FROM mcr.microsoft.com/devcontainers/python:3.11

# Install Node.js 20 for OpenClaw
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install ClawGraph from source
WORKDIR /workspace
COPY . /workspace/
RUN pip install --no-cache-dir -e ".[dev]"

# Install OpenClaw globally
RUN npm install -g @anthropic-ai/openclaw 2>/dev/null || true

# Create ClawGraph config directory
RUN mkdir -p /root/.clawgraph

# Default command
CMD ["bash"]
