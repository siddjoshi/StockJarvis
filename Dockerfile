# Dockerfile - Multi-stage build for StockJarvis

# Build stage - Install dependencies
FROM python:3.11-slim as builder

# Set build arguments
ARG PYTHON_VERSION=3.11

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    gfortran \
    libatlas-base-dev \
    liblapack-dev \
    libblas-dev \
    libhdf5-dev \
    libhdf5-serial-dev \
    pkg-config \
    wget \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install TA-Lib from source (required for ta-lib Python package)
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    # Install additional production dependencies
    pip install --no-cache-dir flower gunicorn

# Runtime stage - Minimal production image
FROM python:3.11-slim as runtime

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    DEBIAN_FRONTEND=noninteractive

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    libatlas3-base \
    liblapack3 \
    libblas3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy TA-Lib library from builder
COPY --from=builder /usr/lib/libta_lib.* /usr/lib/
COPY --from=builder /usr/include/ta-lib/ /usr/include/ta-lib/

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create non-root user for security
RUN groupadd -r jarvis && \
    useradd -r -g jarvis -u 1000 -m -s /bin/bash jarvis && \
    mkdir -p /app /app/logs /app/data && \
    chown -R jarvis:jarvis /app

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=jarvis:jarvis . .

# Create necessary directories with correct permissions
RUN mkdir -p logs data && \
    chown -R jarvis:jarvis logs data && \
    chmod -R 755 logs data

# Switch to non-root user
USER jarvis

# Expose ports
EXPOSE 8000 5555

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command - run FastAPI application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
