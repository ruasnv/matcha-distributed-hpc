import time
import requests
import json
import threading
import subprocess
import os
import tempfile
import shutil

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
            name = nvmlDeviceGetName(handle)
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

# (The OLD execute_docker_task function that was here is NOW DELETED)

def run_subprocess(command, task_id, env_vars=None):
    """Helper function to run a shell command and stream its logs."""
    print(f"[{task_id}] Running command: {command}")

    # Combine current env with task-specific env_vars
    process_env = os.environ.copy()
    if env_vars:
        process_env.update(env_vars)

    process = subprocess.Popen(
        command, 
        shell=True, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True, 
        env=process_env
    )

    output_log = []
    for line in process.stdout:
        print(f"[{task_id}] > {line.strip()}")
        output_log.append(line)

    process.wait()
    return process.returncode, "".join(output_log)

def execute_docker_task(task):
    """
    The new 3-stage task runner: Download, Compute, Upload.
    """
    task_id = task['task_id']
    print(f"[{task_id}] Starting task...")

    # Create a unique temporary directory for this job
    temp_dir = tempfile.mkdtemp(prefix=f"matcha_job_{task_id}_")
    print(f"[{task_id}] Created temp workspace: {temp_dir}")

    s3_env_vars = task['env_vars']
    # !!! IMPORTANT: YOU MUST REPLACE THIS DUMMY URL !!!
    s3_endpoint_url = os.getenv("R2_ENDPOINT_URL", "https://0ad5918c8348ef6bec32eff5f6f17029.r2.cloudflarestorage.com") # Use your real URL

    # We build the 'aws' command to run inside a Docker container
    aws_cli_cmd_base = (
        f"docker run --rm "
        f"-e AWS_ACCESS_KEY_ID=\"{s3_env_vars.get('AWS_ACCESS_KEY_ID')}\" "
        f"-e AWS_SECRET_ACCESS_KEY=\"{s3_env_vars.get('AWS_SECRET_ACCESS_KEY')}\" "
        f"-v \"{temp_dir}\":/workspace " # Mount temp dir
        f"amazon/aws-cli:latest --endpoint-url {s3_endpoint_url}"
    )

    full_stdout = ""
    full_stderr = ""
    script_name = "script.py" # Default script name

    try:
        # --- STAGE 1: DOWNLOAD ---
        report_task_status(task_id, "DOWNLOADING")

        # --- FIX: Replace r2:// with s3:// ---
        s3_script_path = task.get('script_path', '').replace('r2://', 's3://')
        s3_input_path = task.get('input_path', '').replace('r2://', 's3://')

        # Download the main script
        if s3_script_path:
            script_name = os.path.basename(s3_script_path)
            # Use the corrected s3_script_path
            script_cmd = f"{aws_cli_cmd_base} s3 cp \"{s3_script_path}\" /workspace/{script_name}"
            return_code, log = run_subprocess(script_cmd, task_id)
            full_stdout += f"[DOWNLOAD SCRIPT LOG]\n{log}\n"
            if return_code != 0:
                raise Exception(f"Failed to download script: {log}")

        # Download the main input data
        if s3_input_path:
            input_name = os.path.basename(s3_input_path)
            # Use the corrected s3_input_path
            input_cmd = f"{aws_cli_cmd_base} s3 cp \"{s3_input_path}\" /workspace/{input_name}"
            return_code, log = run_subprocess(input_cmd, task_id)
            full_stdout += f"[DOWNLOAD INPUT LOG]\n{log}\n"
            if return_code != 0:
                raise Exception(f"Failed to download input data: {log}")

        # --- STAGE 2: COMPUTE ---
        report_task_status(task_id, "RUNNING")

        gpu_argument = "--gpus all" if "gpu" in task['gpu_id'] else ""
        env_vars_string = " ".join([f"-e {key}=\"{value}\"" for key, value in s3_env_vars.items()])
        
        main_docker_cmd = (
            f"docker run --rm {gpu_argument} "
            f"{env_vars_string} "
            f"-v \"{temp_dir}\":/workspace " # Mount temp dir
            f"{task['docker_image']} "
            f"/bin/sh -c 'cd /workspace && python3 {script_name}'" # Run the script
        )
        
        return_code, log = run_subprocess(main_docker_cmd, task_id)
        full_stdout += f"[COMPUTE LOG]\n{log}\n"
        if return_code != 0:
            raise Exception(f"Compute task failed: {log}")

        # --- STAGE 3: UPLOAD ---
        report_task_status(task_id, "UPLOADING")
        # --- FIX: Replace r2:// with s3:// ---
        s3_output_path = task.get('output_path', '').replace('r2://', 's3://')

        if s3_output_path:
            # Upload everything in the workspace folder to the output path
            # Use the corrected s3_output_path
            upload_cmd = f"{aws_cli_cmd_base} s3 cp /workspace/ \"{s3_output_path}\" --recursive"
            return_code, log = run_subprocess(upload_cmd, task_id)
            full_stdout += f"[UPLOAD LOG]\n{log}\n"
            if return_code != 0:
                raise Exception(f"Failed to upload results: {log}")

        # --- STAGE 4: COMPLETE ---
        print(f"[{task_id}] Task completed successfully.")
        report_task_status(task_id, "COMPLETED", {"stdout": full_stdout})

    except Exception as e:
        print(f"[{task_id}] Task FAILED: {e}")
        full_stderr = str(e)
        report_task_status(task_id, "FAILED", {"stdout": full_stdout, "stderr": full_stderr})

    finally:
        # --- STAGE 5: CLEANUP ---
        try:
            shutil.rmtree(temp_dir)
            print(f"[{task_id}] Cleaned up temp workspace: {temp_dir}")
        except Exception as e:
            print(f"[{task_id}] ERROR: Failed to clean up temp dir {temp_dir}: {e}")
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
                    args=(task,) # Pass the whole task dictionary
                ).start()
            
            # Wait for the next poll
            time.sleep(HEARTBEAT_INTERVAL_SECONDS)
            
        except Exception as e:
            print(f"Error in main loop: {e}. Retrying in 60s...")
            time.sleep(60)

if __name__ == "__main__":
    main()