# OSiri Orchestrator - Docker Image
# Routes tasks to specialized agents (terminal, web, email, slack)

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project (needed for proper imports)
COPY . .

# Set PYTHONPATH
ENV PYTHONPATH=/app:/app/orchestrator
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 9997

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9997/.well-known/agent-card.json || exit 1

# Run the orchestrator
CMD ["python", "/app/orchestrator/orchestrator_a2a_server.py"]
