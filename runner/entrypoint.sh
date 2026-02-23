#!/bin/bash
set -e

echo "📥 Downloading project from R2..."
curl -L "$PROJECT_URL" -o project.zip

echo "📂 Unzipping research code..."
unzip -o project.zip

# Find the actual path of the script automatically
ACTUAL_SCRIPT_PATH=$(find . -maxdepth 2 -name "${SCRIPT_PATH:-main.py}" | head -n 1)

if [ -z "$ACTUAL_SCRIPT_PATH" ]; then
    echo "❌ ERROR: Could not find ${SCRIPT_PATH:-main.py} in /workspace"
    echo "Current directory structure:"
    ls -R
    exit 1
fi

echo "🎯 Found script at: $ACTUAL_SCRIPT_PATH"

# Also find requirements.txt if it exists
REQ_PATH=$(find . -maxdepth 2 -name "requirements.txt" | head -n 1)
if [ -n "$REQ_PATH" ]; then
    echo "📦 Found dependencies at $REQ_PATH. Installing..."
    pip install --no-cache-dir -r "$REQ_PATH"
fi

echo "🚀 Starting Python execution..."
python3 "$ACTUAL_SCRIPT_PATH"