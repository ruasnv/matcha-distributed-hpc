import requests
import argparse
import os
import json

# --- Configuration Loading via Environment Variables ---
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")
API_KEY = os.getenv("CONSUMER_API_KEY") 
if not API_KEY:
    print("FATAL ERROR: CONSUMER_API_KEY environment variable is missing.")
    print("Please set it with: export CONSUMER_API_KEY=your_key_here")
    exit(1)

# --- Core API Functions ---

def submit_task(docker_image, input_path, output_path, script_path, env_vars):
    """Submits a new task (simple or ML) to the Orchestrator."""
    url = f"{ORCHESTRATOR_URL}/consumer/submit_task"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    
    # Parse env_vars from "KEY=VALUE,KEY2=VALUE2"
    env_dict = {}
    if env_vars:
        try:
            for item in env_vars.split(','):
                key, value = item.split('=', 1)
                env_dict[key] = value
        except ValueError:
            print("ERROR: --env format is incorrect. Use 'KEY=VALUE,KEY2=VALUE2'")
            return

    payload = {
        "docker_image": docker_image,
        "input_path": input_path,
        "output_path": output_path,
        "script_path": script_path,
        "env_vars": env_dict
    }

    print(f"Submitting task for image '{docker_image}' to {url}...")
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status() # Raise HTTPError for bad responses
        
        data = response.json()
        print("\n✅ Task Submission Successful!")
        print(f"Task ID: {data.get('task_id')}")
        print(f"Status: {data.get('message')}")
        print("\nUse the task ID to check the status.")
    
    except requests.exceptions.HTTPError as errh:
        print(f"\n❌ HTTP Error: {errh}")
        print(f"Response: {response.text}")
    except requests.exceptions.ConnectionError as errc:
        print(f"\n❌ Connection Error: Could not connect to Orchestrator at {ORCHESTRATOR_URL}.")
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
        print(f"\n❌ Connection Error: Could not connect to Orchestrator at {ORCHESTRATOR_URL}.")
    except requests.exceptions.RequestException as e:
        print(f"\n❌ An unexpected error occurred: {e}")


# --- CLI Setup ---
def main():
    parser = argparse.ArgumentParser(description="Matcha Distributed Compute Consumer CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Submitter command
    parser_submit = subparsers.add_parser('submit', help="Submit a new Docker image task.")
    parser_submit.add_argument('--image', required=True, help="The Docker image to execute (e.g., pytorch/pytorch).")
    parser_submit.add_argument('--input-path', help="S3/R2 path to input data (e.g., r2://my-bucket/dataset.zip)")
    parser_submit.add_argument('--output-path', help="S3/R2 path to upload results to (e.g., r2://my-bucket/results/)")
    parser_submit.add_argument('--script-path', help="S3/R2 path to the main script to run (e.g., r2://my-bucket/train.py)")
    parser_submit.add_argument('--env', help="Comma-separated env vars for the task (e.g., 'KEY=VALUE,KEY2=VALUE2')")

    # Status command
    parser_status = subparsers.add_parser('status', help="Check the status of a submitted task.")
    parser_status.add_argument('--task-id', required=True, help="The ID of the task to check.")

    args = parser.parse_args()

    if args.command == 'submit':
        submit_task(args.image, args.input_path, args.output_path, args.script_path, args.env)
    elif args.command == 'status':
        get_task_status(args.task_id)

if __name__ == '__main__':
    main()