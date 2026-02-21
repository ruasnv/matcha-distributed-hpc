import os
import shutil
import tempfile
import time
import requests
import wsgiref.headers
import docker
import json
import boto3
from botocore.config import Config
from dotenv import load_dotenv
import psutil
import argparse
import platform
try:
    import pynvml # NVIDIA Management Library
    pynvml.nvmlInit()
    HAS_GPU = True
except:
    HAS_GPU = False

# Load .env file if it exists
load_dotenv()

if not hasattr(wsgiref.headers.Headers, 'items'):
    wsgiref.headers.Headers.items = lambda self: self._headers

# --- 1. Configuration ---
# Fallback to the Render URL if the environment variable is missing
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "https://matcha-orchestrator.onrender.com")
PROVIDER_ID = os.getenv("PROVIDER_ID", "ruya-laptop-wsl")
API_KEY = "debug-provider-key"
HEARTBEAT_INTERVAL = 10
headers = {"X-API-Key": API_KEY}

client = docker.from_env()

# Ensure these are also loaded from your local .env or set directly
s3_client = boto3.client(
    's3',
    endpoint_url=os.getenv('R2_ENDPOINT_URL'),
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
    config=Config(
        signature_version='s3v4',
        region_name='auto'
    )
)

# --- GLOBAL DYNAMIC GPU INITIALIZATION ---
GPU_HANDLE = None
GPU_NAME = "Unknown GPU" # Default
# 1. SETUP ARGUMENTS
parser = argparse.ArgumentParser()
parser.add_argument("--enroll", help="The 6-digit token from your Matcha Dashboard")
args = parser.parse_args()

try:
    pynvml.nvmlInit()
    GPU_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(0)
    
    # DYNAMIC DETECTION: Get the real name from the driver
    name_raw = pynvml.nvmlDeviceGetName(GPU_HANDLE)
    GPU_NAME = name_raw.decode('utf-8') if isinstance(name_raw, bytes) else str(name_raw)
    
    print(f"Dynamic Hardware Detection: Found {GPU_NAME}")
except Exception as e:
    print(f"GPU Detection skipped (CPU Only Mode): {e}")

def enroll_device(token):
    print(f"Attempting to link this device to your Matcha account...")
    
    # We send the token to the backend to get our USER_ID
    # This is much safer than hardcoding it!
    response = requests.post(f"{ORCHESTRATOR_URL}/provider/enroll", json={
        "token": token,
        "provider_id": PROVIDER_ID
    })
    
    if response.status_code == 200:
        assigned_user_id = response.json().get('user_id')
        print(f"Success! Device linked to User: {assigned_user_id}")
        return assigned_user_id
    else:
        print(f"Enrollment failed: {response.json().get('error')}")
        exit(1)

# 2. RUNTIME LOGIC
current_user_id = os.getenv("USER_ID") # Try to get from local .env

if args.enroll:
    current_user_id = enroll_device(args.enroll)
    # OPTIONAL: Save current_user_id to a local .env file so you don't have to enroll again
        
def get_telemetry():
    cpu_usage = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    
    telemetry = {
        "cpu_load": cpu_usage,
        "ram_used_gb": round(ram.used / (1024**3), 2),
        "ram_total_gb": round(ram.total / (1024**3), 2),
        "status": "idle",
        "gpu": None
    }

    if GPU_HANDLE:
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(GPU_HANDLE)
            mem = pynvml.nvmlDeviceGetMemoryInfo(GPU_HANDLE)
            
            telemetry["gpu"] = {
                "name": GPU_NAME,
                "load": int(util.gpu),
                "vram_used": round(mem.used / (1024**3), 2),
                "vram_total": round(mem.total / (1024**3), 2)
            }
        except Exception as e:
            # Handle transient "blips" without losing the name
            telemetry["gpu"] = {"name": GPU_NAME, "load": 0, "status": "offline"}
            
    return telemetry

def register_provider():
    """Register this machine as a worker on the network"""
    url = f"{ORCHESTRATOR_URL}/provider/register"
    print(f"📡 Attempting to register at: {url}")
    
    payload = {
        "provider_id": PROVIDER_ID,
        "gpus": [{"id": "cpu_0", "name": "Standard Worker", "status": "idle"}]
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        res.raise_for_status()
        print(f"Registered successfully as {PROVIDER_ID}")
    except Exception as e:
        print(f"Registration failed: {e}")
        # Don't exit immediately; let's see the error detail
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response Detail: {e.response.text}")
        exit(1)

def send_heartbeat():
    """Sends live telemetry to the Orchestrator."""
    url = f"{ORCHESTRATOR_URL}/provider/heartbeat"
    telemetry = get_telemetry() # The function we added earlier
    
    payload = {
        "provider_id": PROVIDER_ID,
        "telemetry": telemetry
    }
    
    try:
        requests.post(url, json=payload, headers=headers)
        # We don't print here to avoid spamming your terminal every 5 seconds
    except Exception as e:
        print(f"Heartbeat failed: {e}")

def update_task_status(task_id, status, logs=None, result_url=None):
    """Sends task updates back to the orchestrator"""
    url = f"{ORCHESTRATOR_URL}/provider/task_update"
    
    # We pass result_url directly in the payload so the Orchestrator 
    # can save it to the database 'result_url' column.
    payload = {
        "task_id": task_id,
        "status": status,
        "result_url": result_url, # Orchestrator looks for this
        "details": {
            "stdout": logs
        }
    }
    try:
        res = requests.post(url, json=payload, headers=headers)
        res.raise_for_status()
        print(f"Status updated: {status} for Task {task_id}")
    except Exception as e:
        print(f"Failed to update task status: {e}")

# ... (Keep your register_provider, send_heartbeat, get_telemetry, update_task_status functions as they are) ...

def poll_for_task():
    """Polls the orchestrator once for a task. Returns True if task ran, False otherwise."""
    url = f"{ORCHESTRATOR_URL}/provider/get_task"
    
    try:
        response = requests.post(url, json={"provider_id": PROVIDER_ID}, headers=headers)
        data = response.json()
        task = data.get("task")

        if not task:
            # print("💤 No tasks. Sleeping...") # We can silence this to keep logs clean
            return False

        task_id = task['task_id']
        print(f"Assigned Task: {task_id}")
        
        # 1. Setup local temp workspace for this specific task
        result_dir = tempfile.mkdtemp()
        
        try:
            # 2. Start the Docker Container
            print("Booting Docker Container...")
            container = client.containers.run(
                "runner:latest", 
                detach=True,
                environment={
                    "PROJECT_URL": task.get('input_path'),
                    "SCRIPT_PATH": task.get('script_path', 'main.py')
                },
                volumes={result_dir: {'bind': '/outputs', 'mode': 'rw'}}
            )
            
            update_task_status(task_id, "RUNNING")

            # 3. WAIT for the researcher's code to finish
            result = container.wait()
            logs = container.logs().decode('utf-8')
            
            if result['StatusCode'] == 0:
                print(f"Container finished successfully.")
                
                # 4. Check for artifacts (models, plots, data) in /outputs
                result_url = None
                files = os.listdir(result_dir)
                
                if files:
                    print(f"Found {len(files)} result files. Uploading to R2...")
                    zip_name = f"results_{task_id}"
                    shutil.make_archive(zip_name, 'zip', result_dir)
                    
                    artifact_key = f"artifacts/{task_id}.zip"
                    with open(f"{zip_name}.zip", 'rb') as f:
                        s3_client.upload_fileobj(f, os.getenv('R2_BUCKET_NAME'), artifact_key)
                    
                    result_url = s3_client.generate_presigned_url(
                        'get_object', 
                        Params={'Bucket': os.getenv('R2_BUCKET_NAME'), 'Key': artifact_key}, 
                        ExpiresIn=604800
                    )
                    os.remove(f"{zip_name}.zip")
                    
                update_task_status(task_id, "COMPLETED", logs, result_url=result_url)
                print(f"Task {task_id} fully processed.")
            
            else:
                print(f"Task {task_id} Failed inside container.")
                print("-" * 40)
                print("DOCKER LOGS:")
                print(logs) 
                print("-" * 40)
                update_task_status(task_id, "FAILED", logs)
            
            # 6. Cleanup container
            container.remove()

        except Exception as docker_err:
            print(f"Docker/System Error: {docker_err}")
            update_task_status(task_id, "FAILED", f"Provider System Error: {str(docker_err)}")
        
        finally:
            if os.path.exists(result_dir):
                shutil.rmtree(result_dir)
                
        return True # Task was executed

    except Exception as e:
        print(f"Connection Error: {e}")
        return False

# --- MAIN EXECUTION LOOP ---
if __name__ == "__main__":
    register_provider()
    print(f"{PROVIDER_ID} is online and connected to {ORCHESTRATOR_URL}")
    print("Listening for tasks and broadcasting telemetry...")
    
    last_heartbeat_time = 0
    HEARTBEAT_INTERVAL_SECONDS = 5
    POLL_INTERVAL_SECONDS = 10
    
    while True:
        current_time = time.time()
        
        # 1. Fire Heartbeat if it's time
        if current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL_SECONDS:
            send_heartbeat()
            last_heartbeat_time = current_time
            
        # 2. Poll for Tasks
        # We only check for tasks if we aren't currently running one.
        # If poll_for_task() returns True, it means it spent time running a task.
        task_executed = poll_for_task()
        
        # 3. Sleep to prevent CPU thrashing
        if not task_executed:
            time.sleep(1) # Short sleep so the heartbeat timer remains accurate