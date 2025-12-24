#!/bin/bash
# 1. Download the project zip from the URL provided by the Orchestrator
# The Agent will pass the PROJECT_URL as an environment variable
curl -L $PROJECT_URL -o project.zip

# 2. Unzip the code
unzip project.zip

# 3. Run the main script (defaulting to main.py if not specified)
python3 ${SCRIPT_PATH:-main.py}