# MAF Agent (Slack/Gmail) Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY requirements.txt /app/requirements.txt
COPY app/maf_agent/requirements.txt /app/maf_requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN pip install --no-cache-dir -r /app/maf_requirements.txt

# Install additional dependencies for Gmail API
RUN pip install --no-cache-dir \
    google-api-python-client \
    google-auth-httplib2 \
    google-auth-oauthlib

# Copy application code
COPY common/ /app/common/
COPY app/agent_framework/ /app/agent_framework/
COPY app/maf/ /app/app/maf/

# Create symbolic links for imports
RUN ln -s /app/app/maf/maf_mcp /app/maf_mcp
RUN ln -s /app/app/maf/maf_a2a /app/maf_a2a

# Set Python path and environment
ENV PYTHONPATH=/app:/app/app/maf
ENV PYTHONUNBUFFERED=1
ENV APP_AGENT_PORT=9996

# Expose port
EXPOSE 9996

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9996/.well-known/agent-card.json || exit 1

# Run the A2A server
CMD ["python", "-m", "maf_a2a.maf_a2a_server"]

