# ACE Audit Service Dockerfile
# Builds the audit collector and API services

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements (subset needed for audit service)
COPY services/ace-audit/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/audit /app/src/audit
COPY src/__init__.py /app/src/

# Create non-root user for security
RUN useradd -m -u 1000 audit && chown -R audit:audit /app
USER audit

# Default port (overridden by command)
EXPOSE 8081 8082

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8081}/health || exit 1
