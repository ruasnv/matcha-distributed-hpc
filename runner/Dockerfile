# Use a lightweight but powerful ML base
FROM python:3.10-slim

# Install system dependencies for ML and Zipping
RUN apt-get update && apt-get install -y \
    unzip \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Pre-install the "Research Stack"
RUN pip install --no-cache-dir \
    torch \
    numpy \
    pandas \
    scipy \
    transformers \
    requests \
    tqdm

# Create a workspace
WORKDIR /workspace

# This script will be the entrypoint that unzips the project and runs it
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]