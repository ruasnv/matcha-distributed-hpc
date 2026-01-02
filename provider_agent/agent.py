import os
import time
import requests
import docker
import json

# --- 1. Configuration ---
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:5000")
PROVIDER_ID = os.getenv("PROVIDER_ID", "ruya-laptop-1")
API_KEY = "debug-provider-key" # Hardcoded for local stability
HEARTBEAT_INTERVAL = 10

client = docker.from_env()

def register_provider():
    """Register this machine as a worker on the network"""
    url = f"{ORCHESTRATOR_URL}/provider/register"
    # Sending dummy GPU info since NVML is disabled in WSL
    payload = {
        "provider_id": PROVIDER_ID,
        "gpus": [{"id": "cpu_0", "name": "Standard Worker", "status": "idle"}]
    }
    headers = {"X-API-Key": API_KEY}
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        res.raise_for_status()
        print(f"✅ Registered as {PROVIDER_ID}")
    except Exception as e:
        print(f"❌ Registration failed: {e}")
        exit(1)

def update_task_status(task_id, status, logs=""):
    """Tell the orchestrator the task status changed"""
    url = f"{ORCHESTRATOR_URL}/provider/task_update"
    headers = {"X-API-Key": API_KEY}
    payload = {
        "task_id": task_id,
        "status": status,
        "details": {"stdout": logs}
    }
    requests.post(url, json=payload, headers=headers)

def poll_and_run():
    """Main loop: Poll for tasks and execute them"""
    headers = {"X-API-Key": API_KEY}
    url = f"{ORCHESTRATOR_URL}/provider/get_task"
    
    while True:
        try:
            response = requests.post(url, json={"provider_id": PROVIDER_ID}, headers=headers)
            data = response.json()
            task = data.get("task")

            if task:
                task_id = task['task_id']
                print(f"🚀 Assigned Task: {task_id}")
                
                # Start the Docker Container (Standard Kernel)
                # Note: We use 'runner:latest' to match your build name
                try:
                    container = client.containers.run(
                        "runner:latest", 
                        detach=True,
                        environment={
                            "PROJECT_URL": task.get('input_path'), # From R2
                            "SCRIPT_PATH": task.get('script_path', 'main.py')
                        }
                    )
                    
                    update_task_status(task_id, "RUNNING")
                    
                    # Wait for container to finish and get logs
                    result = container.wait()
                    logs = container.logs().decode('utf-8')
                    
                    if result['StatusCode'] == 0:
                        print(f"✅ Task {task_id} Completed!")
                        update_task_status(task_id, "COMPLETED", logs)
                    else:
                        print(f"❌ Task {task_id} Failed! Container Output:")
                        print("-" * 30)
                        print(logs) # This will show if curl failed or python crashed
                        print("-" * 30)
                        update_task_status(task_id, "FAILED", logs)
                    
                    container.remove() # Clean up

                except Exception as docker_err:
                    print(f"Docker Error: {docker_err}")
                    update_task_status(task_id, "FAILED", str(docker_err))

            else:
                print("💤 No tasks. Sleeping...")

        except Exception as e:
            print(f"Connection Error: {e}")
        
        time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    register_provider()
    poll_and_run()