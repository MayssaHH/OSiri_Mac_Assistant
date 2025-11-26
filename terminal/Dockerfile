# OSiri Terminal Agent - Docker Image
# Executes safe terminal commands

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (common terminal tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    tree \
    vim \
    nano \
    zsh \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project (needed for proper imports)
COPY . .

# Set PYTHONPATH so imports work correctly
ENV PYTHONPATH=/app:/app/app:/app/terminal
ENV PYTHONUNBUFFERED=1
ENV TERMINAL_AGENT_PORT=9998

# Create directories that will be used
RUN mkdir -p /workspace /root/Desktop /root/Downloads /root/Documents

# Expose port
EXPOSE 9998

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9998/.well-known/agent-card.json || exit 1

# Run the terminal agent
CMD ["python", "/app/terminal/terminal_a2a/terminal_a2a_server.py"]
