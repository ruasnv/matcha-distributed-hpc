#!/bin/bash
set -e

echo "📥 Downloading project..."
curl -L "$PROJECT_URL" -o project.zip
unzip -o project.zip

# 🚀 THE SMART LOGIC:
# If the user included a requirements.txt, install those libraries on the fly!
if [ -f "requirements.txt" ]; then
    echo "📦 Found requirements.txt. Installing custom dependencies..."
    pip install --no-cache-dir -r requirements.txt
fi

echo "🚀 Starting Python execution: ${SCRIPT_PATH:-main.py}"
python3 "${SCRIPT_PATH:-main.py}"