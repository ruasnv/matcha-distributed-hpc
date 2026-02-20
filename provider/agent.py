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

def get_telemetry():
    """Gathers real-time performance data."""
    cpu_usage = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    
    telemetry = {
        "cpu_load": cpu_usage,
        "ram_used_gb": round(ram.used / (1024**3), 2),
        "ram_total_gb": round(ram.total / (1024**3), 2),
        "status": "idle"
    }

    if HAS_GPU:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, 0)
            
            telemetry["gpu"] = {
                "name": pynvml.nvmlDeviceGetName(handle),
                "load": util.gpu,
                "vram_used": round(mem.used / (1024**3), 2),
                "vram_total": round(mem.total / (1024**3), 2),
                "temp": temp
            }
        except Exception as e:
            print(f"GPU Telemetry failed: {e}")
            
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
        print(f"✅ Registered successfully as {PROVIDER_ID}")
    except Exception as e:
        print(f"❌ Registration failed: {e}")
        # Don't exit immediately; let's see the error detail
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response Detail: {e.response.text}")
        exit(1)

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
        print(f"📊 Status updated: {status} for Task {task_id}")
    except Exception as e:
        print(f"⚠️ Failed to update task status: {e}")

# ... (rest of your polling logic) ...
def poll_and_run():
    """Main loop: Poll for tasks and execute them"""
    url = f"{ORCHESTRATOR_URL}/provider/get_task"
    
    while True:
        try:
            response = requests.post(url, json={"provider_id": PROVIDER_ID}, headers=headers)
            data = response.json()
            task = data.get("task")

            if task:
                task_id = task['task_id']
                print(f"🚀 Assigned Task: {task_id}")
                
                # 1. Setup local temp workspace for this specific task
                result_dir = tempfile.mkdtemp()
                
                try:
                    # 2. Start the Docker Container
                    container = client.containers.run(
                        "runner:latest", 
                        detach=True,
                        environment={
                            "PROJECT_URL": task.get('input_path'),
                            "SCRIPT_PATH": task.get('script_path', 'main.py')
                        },
                        # Map /outputs inside container to our temp result_dir
                        # It should match what the researcher uses!
                        volumes={result_dir: {'bind': '/outputs', 'mode': 'rw'}}
                    )
                    
                    update_task_status(task_id, "RUNNING")

                    # 3. WAIT for the researcher's code to finish
                    result = container.wait()
                    logs = container.logs().decode('utf-8')
                    
                    if result['StatusCode'] == 0:
                        print(f"✅ Container finished successfully.")
                        
                        # 4. Check for artifacts (models, plots, data) in /outputs
                        result_url = None
                        files = os.listdir(result_dir)
                        
                        if files:
                            print(f"📦 Found {len(files)} result files. Uploading to R2...")
                            # Zip the artifacts
                            zip_name = f"results_{task_id}"
                            archive_path = shutil.make_archive(zip_name, 'zip', result_dir)
                            
                            # Upload to R2 artifacts folder
                            artifact_key = f"artifacts/{task_id}.zip"
                            with open(f"{zip_name}.zip", 'rb') as f:
                                s3_client.upload_fileobj(f, os.getenv('R2_BUCKET_NAME'), artifact_key)
                            
                            # Generate a long-term link for the researcher (7 days)
                            result_url = s3_client.generate_presigned_url(
                                'get_object', 
                                Params={'Bucket': os.getenv('R2_BUCKET_NAME'), 'Key': artifact_key}, 
                                ExpiresIn=604800
                            )
                            # Clean up the local zip file after upload
                            os.remove(f"{zip_name}.zip")
                            update_task_status(task_id, "COMPLETED", logs, result_url=result_url)

                            # 5. Report success + logs + download link
                            print(f"🎉 Task {task_id} fully processed.")
                    
                    else:
                        print(f"❌ Task {task_id} Failed inside container.")
                        print("-" * 40)
                        print("DOCKER LOGS:")
                        print(logs) # <--- ADD THIS LINE TO SEE THE ERROR
                        print("-" * 40)
                        update_task_status(task_id, "FAILED", logs)
                    
                    # 6. Cleanup container
                    container.remove()

                except Exception as docker_err:
                    print(f"Docker/System Error: {docker_err}")
                    # CRITICAL: If Docker fails to even start, we MUST tell the Orchestrator
                    update_task_status(task_id, "FAILED", f"Provider System Error: {str(docker_err)}")
                
                finally:
                    if os.path.exists(result_dir):
                        shutil.rmtree(result_dir)

            else:
                print("💤 No tasks. Sleeping...")

        except Exception as e:
            print(f"Connection Error: {e}")
        
        time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    register_provider()
    poll_and_run()