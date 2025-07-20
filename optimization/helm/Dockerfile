# Multi-stage build for smaller final image
FROM python:3.9-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    git \
    curl \
    build-essential \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.9-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user first
RUN groupadd -g 1000 optimizer && \
    useradd -r -u 1000 -g optimizer optimizer

# Create necessary directories with correct permissions
RUN mkdir -p /app /models /logs /config /data && \
    chown -R optimizer:optimizer /app /models /logs /config /data

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder --chown=optimizer:optimizer /root/.local /home/optimizer/.local

# Copy application code
COPY --chown=optimizer:optimizer src/energy_optimization_controller.py ./
COPY --chown=optimizer:optimizer src/advanced_optimization.py ./
COPY --chown=optimizer:optimizer src/main.py ./

# Create a startup script
RUN echo '#!/bin/bash' > /app/startup.sh && \
    echo 'set -e' >> /app/startup.sh && \
    echo '' >> /app/startup.sh && \
    echo '# Check if models directory is mounted and writable' >> /app/startup.sh && \
    echo 'if [ -w "/models" ]; then' >> /app/startup.sh && \
    echo '    echo "Models directory is writable"' >> /app/startup.sh && \
    echo 'else' >> /app/startup.sh && \
    echo '    echo "Warning: Models directory is not writable"' >> /app/startup.sh && \
    echo 'fi' >> /app/startup.sh && \
    echo '' >> /app/startup.sh && \
    echo '# Start the application' >> /app/startup.sh && \
    echo 'exec python -u main.py' >> /app/startup.sh && \
    chmod +x /app/startup.sh && \
    chown optimizer:optimizer /app/startup.sh

# Set Python path to include user packages
ENV PATH=/home/optimizer/.local/bin:"${PATH}"
ENV PYTHONPATH=/home/optimizer/.local/lib/python3.9/site-packages:"${PYTHONPATH}"

# Environment variables for the application
ENV PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO \
    MODEL_PATH=/models \
    CONFIG_PATH=/config \
    DATA_PATH=/data \
    PROMETHEUS_URL=http://prometheus:9090 \
    OPTIMIZATION_ENABLED=true \
    DRY_RUN=false

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/metrics || exit 1

# Switch to non-root user
USER optimizer

# Expose metrics port
EXPOSE 8080

# Use the startup script
ENTRYPOINT ["/app/startup.sh"]
