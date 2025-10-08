# Stage 1: Build dependencies
FROM python:3.10-slim AS builder

# Set the working directory
WORKDIR /app

# Copy only the requirements file first to take advantage of Docker caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------

# Stage 2: Final runtime image
FROM python:3.10-slim

# Install curl so the healthcheck can work
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the actual application code
COPY . /app

# The orchestrator is running Flask on port 5000 internally
EXPOSE 5000

# Command to run the Orchestrator service
CMD ["python", "app.py"]