FROM python:3.13-slim

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
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/osm_data
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]