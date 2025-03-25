FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y \
    netcat-openbsd \
    build-essential \
    cmake \
    libboost-dev \
    libexpat1-dev \
    zlib1g-dev \
    libbz2-dev \
    libsparsehash-dev \
    libgdal-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install curl for health checks
RUN apt-get update && apt-get install -y curl netcat-openbsd && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Add a health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

# Set up entrypoint script
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]