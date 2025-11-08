import time
import requests
import json
import threading
import subprocess
import os

# --- NVML (GPU Detection) ---
try:
    from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex, \
                       nvmlDeviceGetName, nvmlDeviceGetMemoryInfo, nvmlShutdown, \
                       NVMLError
    NVML_AVAILABLE = True
except Exception:
    print("WARNING: NVML (NVIDIA driver) not found. GPU status disabled.")
    NVML_AVAILABLE = False

# --- Configuration ---
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL")
PROVIDER_ID = os.getenv("PROVIDER_ID")
API_KEY = os.getenv("API_KEY")
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", 15))

if not all([ORCHESTRATOR_URL, PROVIDER_ID, API_KEY]):
    print("FATAL ERROR: Missing env vars: ORCHESTRATOR_URL, PROVIDER_ID, or API_KEY")
    exit(1)

# --- GPU Info Function ---
def get_gpu_info():
    gpus_data = []
    if not NVML_AVAILABLE:
        print("WARNING: Registering as CPU-only worker (NVML not available).")
        gpus_data.append({
            "id": "cpu_0", "name": "CPU Worker",
            "total_memory_mb": 0, "free_memory_mb": 0,
            "status": "idle"
        })
        return gpus_data
    
    try:
        nvmlInit()
        device_count = nvmlDeviceGetCount()
        for i in range(device_count):
            handle = nvmlDeviceGetHandleByIndex(i)
            name = nvmlDeviceGetName(handle).decode('utf-8')
            memory_info = nvmlDeviceGetMemoryInfo(handle)
            gpus_data.append({
                "id": f"gpu_{i}",
                "name": name,
                "total_memory_mb": round(memory_info.total / (1024**2), 2),
                "free_memory_mb": round(memory_info.free / (1024**2), 2),
                "status": "idle" # Always register as idle
            })
    except NVMLError as error:
        print(f"Error querying NVIDIA GPUs: {error}")
    finally:
        try:
            nvmlShutdown()
        except NVMLError: pass
    
    if not gpus_data:
         print("WARNING: NVML found but no GPUs detected. Registering as CPU-only.")
         gpus_data.append({
            "id": "cpu_0", "name": "CPU Worker",
            "total_memory_mb": 0, "free_memory_mb": 0,
            "status": "idle"
        })
    
    return gpus_data

# --- Orchestrator Communication ---

def register_provider():
    url = f"{ORCHESTRATOR_URL}/provider/register"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    payload = {"provider_id": PROVIDER_ID, "gpus": get_gpu_info()}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print(f"Provider registration successful: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Provider registration failed: {e}")
        return False

def report_task_status(task_id, status, details=None):
    url = f"{ORCHESTRATOR_URL}/provider/task_update"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    payload = {"task_id": task_id, "status": status, "details": details or {}}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print(f"Reported task {task_id} status '{status}' to Orchestrator.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to report task {task_id} status '{status}': {e}")

def get_task_from_orchestrator():
    url = f"{ORCHESTRATOR_URL}/provider/get_task"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    payload = {"provider_id": PROVIDER_ID}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"Heartbeat/Poll successful: {data.get('message')}")
        return data.get('task') # Returns None if no task
    except requests.exceptions.RequestException as e:
        print(f"Failed to poll for tasks: {e}")
        return None

# --- Task Execution ---

def execute_docker_task(task_id, docker_image, gpu_id):
    print(f"[{task_id}] Starting task. Image: {docker_image} on GPU: {gpu_id}")
    
    # Report RUNNING immediately
    report_task_status(task_id, "RUNNING")
    
    gpu_argument = "--gpus all" if NVML_AVAILABLE and "gpu" in gpu_id else ""
    docker_command = f"docker run --rm {gpu_argument} {docker_image}"
    print(f"[{task_id}] Executing: {docker_command}")
    
    try:
        result = subprocess.run(
            docker_command,
            shell=True, 
            capture_output=True,
            text=True,
            check=True
        )
        print(f"[{task_id}] Task completed. Stdout: {result.stdout[:200]}...")
        report_task_status(task_id, "COMPLETED", {
            "stdout": result.stdout,
            "stderr": result.stderr
        })
    except subprocess.CalledProcessError as e:
        print(f"[{task_id}] Task FAILED. Stderr: {e.stderr[:500]}...")
        report_task_status(task_id, "FAILED", {
            "stdout": e.stdout,
            "stderr": e.stderr
        })
    except Exception as e:
        print(f"[{task_id}] Task FAILED (Unexpected error): {e}")
        report_task_status(task_id, "FAILED", {"stderr": str(e)})

# --- Main Worker Loop ---

def main():
    print(f"Starting Provider Agent (ID: {PROVIDER_ID})...")
    print(f"Targeting Orchestrator at: {ORCHESTRATOR_URL}")

    if not register_provider():
        print("Initial registration failed. Retrying in 60s...")
        time.sleep(60)
        if not register_provider():
            print("Registration failed again. Exiting.")
            exit(1)
            
    print("Registration successful. Starting worker loop...")
    
    while True:
        try:
            task = get_task_from_orchestrator()
            
            if task:
                # Run the task in a new thread to not block the main loop
                threading.Thread(
                    target=execute_docker_task,
                    args=(task['task_id'], task['docker_image'], task['gpu_id'])
                ).start()
            
            # Wait for the next poll
            time.sleep(HEARTBEAT_INTERVAL_SECONDS)
            
        except Exception as e:
            print(f"Error in main loop: {e}. Retrying in 60s...")
            time.sleep(60)

if __name__ == "__main__":
    main()