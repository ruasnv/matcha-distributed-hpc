# Start from the official NVIDIA CUDA image that works on your system
FROM nvidia/cuda:12.1.1-base-ubuntu22.04

# Set the working directory
WORKDIR /app

# Install Python, pip, and the Docker client using apt-get
# ENV DEBIAN_FRONTEND=noninteractive is used to prevent installation prompts
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip docker.io && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the actual application code
COPY . /app

# Command to run the Provider Agent using python3
CMD ["python3", "agent.py"]