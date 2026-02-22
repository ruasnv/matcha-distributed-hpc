#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "Downloading project from R2..."
# FIX: Wrap the URL in double quotes to handle '&' and '?'
curl -L "$PROJECT_URL" -o project.zip

echo "Unzipping research code..."
unzip -o project.zip

echo "Starting Python execution: ${SCRIPT_PATH:-main.py}"
python3 "${SCRIPT_PATH:-main.py}"