import time
import requests
import json
import threading
import subprocess
import os

from flask import Flask, request, jsonify

# Attempt to import pynvml, but wrap it in a try/except block.
# This ensures the agent can still run and report the error if NVML drivers are missing,
# which is the expected behavior when Docker is not configured with GPU access yet.
try:
    from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex, \
                       nvmlDeviceGetName, nvmlDeviceGetMemoryInfo, nvmlShutdown, \
                       NVMLError
    NVML_AVAILABLE = True
except ImportError:
    print("WARNING: pynvml not installed or found. GPU status will not be available.")
    NVML_AVAILABLE = False
except Exception as e:
    print(f"WARNING: NVML initialization failed: {e}. GPU status disabled.")
    NVML_AVAILABLE = False


# --- Configuration Loading via Environment Variables ---
# 1. Orchestrator URL (Internal Docker Name + Port)
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL")
if not ORCHESTRATOR_URL:
    # This is critical for internal Docker communication.
    # Fallback to the service name and expected default Flask port.
    ORCHESTRATOR_URL = "http://orchestrator:5000" 
    print(f"WARNING: ORCHESTRATOR_URL not set. Defaulting to {ORCHESTRATOR_URL}")

# 2. Provider ID (Required)
PROVIDER_ID = os.getenv("PROVIDER_ID")
if not PROVIDER_ID:
    print("FATAL ERROR: PROVIDER_ID environment variable is required and missing.")
    # Exit later in __main__ if still missing.

# 3. API Key
API_KEY = os.getenv("API_KEY", "default-api-key") # Use a robust default if not set

# 4. Heartbeat Interval (Seconds)
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", 10))


# --- Flask App Setup for Agent ---
# The Agent needs its own port (5001) to receive tasks from the Orchestrator
AGENT_PORT = 5001 
app = Flask(__name__)

# --- NVML GPU Info ---
def get_gpu_info():
    """Detects available NVIDIA GPUs and their current status."""
    gpus_data = []
    if not NVML_AVAILABLE:
        print("Error querying NVIDIA GPUs: NVML Shared Library Not Found (NVML_AVAILABLE is False)")
        # Return a mock GPU if NVML is not available to allow agent to start
        return [{
            "id": "mock_cpu_0",
            "name": "CPU Worker (No GPU)",
            "total_memory_mb": 0,
            "free_memory_mb": 0,
            "status": "idle"
        }]
    
    # Existing NVML logic remains the same
    try:
        nvmlInit()
        device_count = nvmlDeviceGetCount()
        for i in range(device_count):
            handle = nvmlDeviceGetHandleByIndex(i)
            name = nvmlDeviceGetName(handle)
            memory_info = nvmlDeviceGetMemoryInfo(handle)
            total_memory_mb = memory_info.total / (1024 * 1024)
            free_memory_mb = memory_info.free / (1024 * 1024)

            gpus_data.append({
                "id": f"gpu_{i}",
                "name": name.decode('utf-8') if isinstance(name, bytes) else name, # Ensure name is string
                "total_memory_mb": round(total_memory_mb, 2),
                "free_memory_mb": round(free_memory_mb, 2),
                "status": "idle"
            })
    except NVMLError as error:
        print(f"Error querying NVIDIA GPUs: {error}")
    finally:
        try:
            nvmlShutdown()
        except NVMLError:
            pass
    return gpus_data

# --- Orchestrator Communication ---
def register_provider(gpus_data):
    url = f"{ORCHESTRATOR_URL}/provider/register"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    payload = {"provider_id": PROVIDER_ID, "gpus": gpus_data}
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Provider registration successful: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        # Crucial fix: The Provider's internal IP (e.g., 172.18.0.3) must be 
        # sent to the orchestrator so the orchestrator can call /run_task
        # In a real Docker Compose network, the Orchestrator can call the 
        # Agent using the service name 'provider'. 
        # For now, let's assume the registration API should work.
        print(f"Provider registration failed connecting to {url}: {e}")
        return False

def send_heartbeat(gpus_data):
    url = f"{ORCHESTRATOR_URL}/provider/heartbeat"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    payload = {"provider_id": PROVIDER_ID, "gpus": gpus_data}
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Heartbeat successful: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Heartbeat failed connecting to {url}: {e}")
        return False

def report_task_status(task_id, status, details=None):
    """Reports task status back to the Orchestrator."""
    url = f"{ORCHESTRATOR_URL}/provider/task_update"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    payload = {
        "task_id": task_id,
        "status": status,
        "details": details
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Reported task {task_id} status '{status}' to Orchestrator: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to report task {task_id} status '{status}' to Orchestrator: {e}")

# --- Task Execution Logic ---
def execute_docker_task(task_id, docker_image, gpu_id):
    """
    Executes a Docker container with GPU access.
    Runs in a separate thread.
    """
    print(f"[{task_id}] Attempting to run Docker image: {docker_image} on GPU: {gpu_id}")

    # Use the specific GPU device mapping if pynvml detected a GPU, 
    # otherwise default to 'all' or skip the --gpus flag if running a CPU job.
    if NVML_AVAILABLE:
        # Note: If NVML correctly detects the GPU ID (e.g., 0, 1), you can map it.
        # For simplicity and robustness inside a Docker container that already has
        # the NVIDIA runtime enabled, '--gpus all' is often the best choice for MVP.
        gpu_argument = "--gpus all"
    else:
        # If no GPU/NVML, don't pass the --gpus argument.
        gpu_argument = "" 

    docker_command = f"docker run --rm {gpu_argument} {docker_image}" 
    print(f"[{task_id}] Executing command: {docker_command}")
    
    try:
        # Report status as RUNNING
        report_task_status(task_id, "RUNNING", {"message": f"Starting container {docker_image}"})

        # Execute the command
        result = subprocess.run(
            docker_command,
            shell=True, 
            capture_output=True,
            text=True,
            check=True
        )

        print(f"[{task_id}] Docker command completed. Stdout:\n{result.stdout}")
        
        # Report status as COMPLETED
        report_task_status(task_id, "COMPLETED", {
            "stdout": result.stdout,
            "stderr": result.stderr
        })

    except Exception as e: # <-- This will catch ALL errors, including FileNotFoundError
        print(f"[{task_id}] An unexpected error occurred: {e}")
        report_task_status(task_id, "FAILED", {"error_message": str(e)})

# --- Flask Routes for Agent ---
@app.route('/run_task', methods=['POST'])
def handle_run_task():
    # The Orchestrator will call this API when it schedules a task for this Provider
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    task_id = data.get('task_id')
    docker_image = data.get('docker_image')
    gpu_id = data.get('gpu_id')

    if not all([task_id, docker_image, gpu_id]):
        return jsonify({"error": "Missing task_id, docker_image, or gpu_id"}), 400

    print(f"Received request to run task {task_id} with image {docker_image} on GPU {gpu_id}")

    # Run the Docker task in a separate thread to prevent blocking the HTTP response
    threading.Thread(target=execute_docker_task, args=(task_id, docker_image, gpu_id)).start()

    return jsonify({"message": f"Task {task_id} received and queued for execution."}), 200

# --- Background Heartbeat Thread ---
def start_heartbeat_thread():
    """Starts a separate thread for sending periodic heartbeats."""
    while True:
        gpus = get_gpu_info()
        send_heartbeat(gpus)
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)

# --- Main entry point for Flask app ---
if __name__ == '__main__':
    if not PROVIDER_ID:
        print("Agent cannot start: PROVIDER_ID is missing from environment.")
        exit(1)

    print(f"Starting Provider Agent Flask server (ID: {PROVIDER_ID})...")
    print(f"Targeting Orchestrator at: {ORCHESTRATOR_URL}")

    # Initial registration before starting the server
    gpus_on_startup = get_gpu_info()
    if not register_provider(gpus_on_startup):
        print("Initial registration failed. Exiting.")
        exit(1)

    # Start the heartbeat thread
    threading.Thread(target=start_heartbeat_thread, daemon=True).start()

    # Run the Flask app on 0.0.0.0, using the dedicated AGENT_PORT (5001)
    app.run(host='0.0.0.0', port=AGENT_PORT, debug=False)
