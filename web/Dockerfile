# OSiri Web Agent - Docker Image
# Web search and scraping capabilities

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

# Set PYTHONPATH so imports work correctly
ENV PYTHONPATH=/app:/app/app:/app/web
ENV PYTHONUNBUFFERED=1
ENV WEB_AGENT_PORT=9999

# Expose port
EXPOSE 9999

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9999/.well-known/agent-card.json || exit 1

# Run the web agent
CMD ["python", "/app/web/web_a2a/web_a2a_server.py"]
