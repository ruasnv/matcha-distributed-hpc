import requests
import argparse
import os
import json

# --- Configuration Loading via Environment Variables ---
# The CLI connects to the Orchestrator via the host port (8000)
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")

# API Key must match the ORCHESTRATOR_API_KEY_CONSUMERS set in docker-compose.yml
API_KEY = os.getenv("CONSUMER_API_KEY") 
if not API_KEY:
    print("FATAL ERROR: CONSUMER_API_KEY environment variable is missing.")
    exit(1)

# --- Core API Functions ---

def submit_task(docker_image):
    """Submits a new task to the Orchestrator."""
    url = f"{ORCHESTRATOR_URL}/consumer/submit_task"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    
    payload = {
        "docker_image": docker_image,
        # Add any other submission data needed (e.g., resources, priority)
    }

    print(f"Submitting task for image '{docker_image}' to {url}...")
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        
        data = response.json()
        print("\n✅ Task Submission Successful!")
        print(f"Task ID: {data.get('task_id')}")
        print(f"Status: {data.get('message')}")
        print("\nUse the task ID to check the status.")
    
    except requests.exceptions.HTTPError as errh:
        print(f"\n❌ HTTP Error: {errh}")
        print(f"Response: {response.text}")
    except requests.exceptions.ConnectionError as errc:
        print(f"\n❌ Connection Error: Could not connect to Orchestrator at {ORCHESTRATOR_URL}. Is Docker Compose running?")
        print(f"Error details: {errc}")
    except requests.exceptions.RequestException as e:
        print(f"\n❌ An unexpected error occurred: {e}")

def get_task_status(task_id):
    """Retrieves the status of a specific task."""
    url = f"{ORCHESTRATOR_URL}/consumer/task_status/{task_id}"
    headers = {"X-API-Key": API_KEY}

    print(f"Checking status for Task ID: {task_id} at {url}...")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        print("\n--- Task Status Report ---")
        print(json.dumps(data, indent=4))
        print("--------------------------")
        
    except requests.exceptions.HTTPError as errh:
        print(f"\n❌ HTTP Error: {errh}")
        if response.status_code == 404:
            print(f"Task ID '{task_id}' not found.")
        else:
            print(f"Response: {response.text}")
    except requests.exceptions.ConnectionError as errc:
        print(f"\n❌ Connection Error: Could not connect to Orchestrator at {ORCHESTRATOR_URL}. Is Docker Compose running?")
    except requests.exceptions.RequestException as e:
        print(f"\n❌ An unexpected error occurred: {e}")


# --- CLI Setup ---
def main():
    parser = argparse.ArgumentParser(description="Matcha Distributed Compute Consumer CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Submitter command
    parser_submit = subparsers.add_parser('submit', help="Submit a new Docker image task.")
    parser_submit.add_argument('--docker-image', required=True, help="The Docker image name to execute (e.g., python:3.10-slim).")

    # Status command
    parser_status = subparsers.add_parser('status', help="Check the status of a submitted task.")
    parser_status.add_argument('--task-id', required=True, help="The ID of the task to check.")

    args = parser.parse_args()

    if args.command == 'submit':
        submit_task(args.docker_image)
    elif args.command == 'status':
        get_task_status(args.task_id)

if __name__ == '__main__':
    main()
