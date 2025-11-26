# OSiri UI - Docker Image
# A chat interface for OSiri Assistant

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
COPY ui/requirements.txt ./ui/
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r ui/requirements.txt

# Copy application code
COPY ui/ ./ui/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# Expose port
EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7860/ || exit 1

# Run the UI
WORKDIR /app/ui
CMD ["python", "app.py"]
