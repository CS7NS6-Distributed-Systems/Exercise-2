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

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install pytest pytest-cov pytest-flask

COPY . .

COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
