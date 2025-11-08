# Stage 1: Build dependencies
FROM python:3.10-slim AS builder

WORKDIR /app

# We need gunicorn for the production server
# Make sure gunicorn is in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.10-slim

# Install curl so the healthcheck can work
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the actual application code
COPY . /app

EXPOSE 5000

# --- THIS IS THE KEY CHANGE ---
# Use Gunicorn as the production-ready start command
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:create_app()"]