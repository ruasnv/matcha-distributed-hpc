#services.py
from datetime import datetime
from flask import current_app, g
from . import get_db
import threading
import jsonpickle
import uuid # For generating unique task IDs
import threading
import requests # For making requests to Provider Agents
import json
import sqlite3


# --- Provider Management ---
def register_or_update_provider(provider_id, gpus, address):
    db = get_db()
    cursor = db.cursor()
    
    # Serialize GPUs list to JSON string for storage
    gpus_json = jsonpickle.encode(gpus, unpicklable=False)

    try:
        # Try to update first
        cursor.execute(
            """UPDATE providers SET gpus = ?, address = ?, last_seen = CURRENT_TIMESTAMP, status = 'active' WHERE id = ?""",
            (gpus_json, address, provider_id)
        )
        if cursor.rowcount == 0:
            # If no row was updated, insert new provider
            cursor.execute(
                """INSERT INTO providers (id, name, gpus, address, last_seen, status) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'active')""",
                (provider_id, provider_id, gpus_json, address) # Using provider_id as name for now
            )
            message = f"Provider {provider_id} registered successfully."
        else:
            message = f"Provider {provider_id} updated successfully."
        
        db.commit()
        print(f"DB: {message} GPUs: {gpus}")
        return True, message
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error registering/updating provider {provider_id}: {e}")
        return False, f"Database error: {e}"

def update_provider_heartbeat(provider_id, gpus=None):
    db = get_db()
    cursor = db.cursor()
    
    update_gpus_sql = ""
    update_gpus_params = []
    if gpus is not None:
        gpus_json = jsonpickle.encode(gpus, unpicklable=False)
        update_gpus_sql = ", gpus = ?"
        update_gpus_params.append(gpus_json)

    try:
        cursor.execute(
            f"UPDATE providers SET last_seen = CURRENT_TIMESTAMP, status = 'active'{update_gpus_sql} WHERE id = ?",
            (*update_gpus_params, provider_id)
        )
        if cursor.rowcount == 0:
            # Provider not found, maybe it was deleted or restarted without proper registration
            print(f"DB: Heartbeat from unknown provider {provider_id}.")
            return False, f"Provider {provider_id} not found. Please register first."
        
        db.commit()
        print(f"DB: Heartbeat from {provider_id} received.")
        return True, f"Heartbeat from {provider_id} received."
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error updating heartbeat for {provider_id}: {e}")
        return False, f"Database error: {e}"

def get_provider(provider_id):
    db = get_db()
    provider_row = db.execute('SELECT * FROM providers WHERE id = ?', (provider_id,)).fetchone()
    if provider_row:
        # Deserialize GPUs back to Python list
        provider_dict = dict(provider_row)
        provider_dict['gpus'] = jsonpickle.decode(provider_dict['gpus'])
        return provider_dict
    return None

def get_all_providers():
    db = get_db()
    provider_rows = db.execute('SELECT * FROM providers').fetchall()
    providers_list = []
    for row in provider_rows:
        provider_dict = dict(row)
        provider_dict['gpus'] = jsonpickle.decode(provider_dict['gpus'])
        providers_list.append(provider_dict)
    return providers_list

def schedule_task(consumer_id, docker_image, gpu_requirements):
    db = get_db()
    cursor = db.cursor()
    task_id = str(uuid.uuid4())

    # Serialize gpu_requirements
    gpu_requirements_json = jsonpickle.encode(gpu_requirements, unpicklable=False)

    target_provider_id = None
    target_gpu_info = None

    providers_info = get_all_providers()
    for provider_info in providers_info:
        if provider_info['status'] == 'active' and provider_info['gpus']:
            target_provider_id = provider_info['id']
            target_gpu_info = provider_info['gpus'][0]
            break

    if not target_provider_id:
        return False, "No available GPUs at the moment. Please try again later.", None

    gpu_assigned_json = jsonpickle.encode(target_gpu_info, unpicklable=False)

    try:
        cursor.execute(
            """INSERT INTO tasks (id, consumer_id, docker_image, gpu_requirements, provider_id, gpu_assigned, status, submission_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (task_id, consumer_id, docker_image, gpu_requirements_json, target_provider_id, gpu_assigned_json, 'QUEUED')
        )
        db.commit()
        print(f"DB: Task {task_id} queued for provider {target_provider_id} on GPU {target_gpu_info['id']}.")

        # --- IMPORTANT CHANGE HERE ---
        # Pass the Flask application instance to the thread's target function
        threading.Thread(target=_dispatch_task_to_provider, args=(
            current_app._get_current_object(), # Pass the app instance
            task_id,
            docker_image,
            target_provider_id,
            get_provider(target_provider_id)['address'],
            target_gpu_info['id']
        )).start()

        return True, f"Task {task_id} submitted and queued for execution.", task_id
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error scheduling task {task_id}: {e}")
        return False, f"Database error: {e}", None


# --- Modified _dispatch_task_to_provider function ---
# It now accepts `app` as its first argument
def _dispatch_task_to_provider(app, task_id, docker_image, provider_id, provider_address, gpu_id):
    """
    Internal function to send the task execution command to the Provider Agent.
    This runs in a separate thread and now pushes an application context.
    """
    # Push an application context for this thread
    with app.app_context():
        url = f"http://{provider_address}:5001/run_task"
        headers = {"Content-Type": "application/json"}
        payload = {
            "task_id": task_id,
            "docker_image": docker_image,
            "gpu_id": gpu_id
        }

        # Update task status to RUNNING in DB immediately upon dispatch attempt
        # This call is now safe because we are inside the app context
        update_task_status(task_id, 'RUNNING', {'start_time': datetime.now().isoformat()})

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            response.raise_for_status()
            print(f"Task {task_id} dispatched to provider {provider_id} successfully. Agent response: {response.json()}")
        except requests.exceptions.RequestException as e:
            print(f"Error dispatching task {task_id} to provider {provider_id}: {e}")
            error_details = {"error_message": str(e)}
            if e.response:
                error_details["stderr"] = e.response.text
            # This call is now safe because we are inside the app context
            update_task_status(task_id, 'FAILED', error_details)

def update_task_status(task_id, status, details=None):
    db = get_db()
    cursor = db.cursor()
    
    update_fields = ["status = ?", "last_update = CURRENT_TIMESTAMP"]
    update_params = [status]
    
    if details:
        # Special handling for stdout/stderr if they are large
        if 'stdout' in details:
            update_fields.append("stdout = ?")
            update_params.append(details['stdout'])
            del details['stdout'] # Don't put it in general details json
        if 'stderr' in details:
            update_fields.append("stderr = ?")
            update_params.append(details['stderr'])
            del details['stderr']

        # Store remaining details as JSON
        update_fields.append("error_message = ?") # Renaming to error_message if it's the main detail
        update_params.append(json.dumps(details)) # Use standard json for simple dicts

    if status in ['COMPLETED', 'FAILED']:
        update_fields.append("end_time = CURRENT_TIMESTAMP")
    
    update_query = f"UPDATE tasks SET {', '.join(update_fields)} WHERE id = ?"
    update_params.append(task_id)

    try:
        cursor.execute(update_query, tuple(update_params))
        if cursor.rowcount == 0:
            print(f"DB: Attempted to update status for unknown task {task_id}.")
            return False, "Task not found."
        db.commit()
        print(f"DB: Task {task_id} status updated to {status}.")
        return True, "Task status updated."
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error updating task {task_id} status: {e}")
        return False, f"Database error: {e}"

def get_task_status(task_id):
    db = get_db()
    task_row = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if task_row:
        task_dict = dict(task_row)
        # Deserialize JSON fields
        if task_dict['gpu_requirements']:
            task_dict['gpu_requirements'] = jsonpickle.decode(task_dict['gpu_requirements'])
        if task_dict['gpu_assigned']:
            task_dict['gpu_assigned'] = jsonpickle.decode(task_dict['gpu_assigned'])
        # error_message and stdout/stderr are now plain text
        # if task_dict['error_message']: # If error_message holds JSON details
        #     task_dict['details'] = json.loads(task_dict['error_message'])
        return task_dict
    return None

def get_all_tasks():
    db = get_db()
    task_rows = db.execute('SELECT * FROM tasks ORDER BY submission_time DESC').fetchall()
    tasks_list = []
    for row in task_rows:
        task_dict = dict(row)
        if task_dict['gpu_requirements']:
            task_dict['gpu_requirements'] = jsonpickle.decode(task_dict['gpu_requirements'])
        if task_dict['gpu_assigned']:
            task_dict['gpu_assigned'] = jsonpickle.decode(task_dict['gpu_assigned'])
        tasks_list.append(task_dict)
    return tasks_list

"""# New in-memory store for tasks
_tasks = {} # Stores: {task_id: {'consumer_id': ..., 'docker_image': ..., 'gpu_assigned': {...}, 'provider_id': ..., 'status': 'queued/running/completed/failed'}}
_tasks_lock = threading.Lock()

# ... (existing register_or_update_provider and update_provider_heartbeat functions) ...

def schedule_task(consumer_id, docker_image, gpu_requirements):
    task_id = str(uuid.uuid4()) # Generate a unique ID for the task

    with _providers_lock:
        # MVP Scheduling: Find the first available provider with a GPU
        # In later phases, this will be much smarter (matching gpu_requirements, load balancing)
        target_provider_id = None
        target_gpu_info = None

        for provider_id, provider_info in _providers.items():
            # For MVP, just assume the provider has an available GPU if it's 'active'
            # and hasn't explicitly reported no GPUs.
            # In Phase 2/3, we'd check actual free_memory_mb, and mark GPUs as 'in_use'.
            if provider_info['status'] == 'active' and provider_info['gpus']:
                target_provider_id = provider_id
                target_gpu_info = provider_info['gpus'][0] # Pick the first GPU reported
                break

        if not target_provider_id:
            return False, "No available GPUs at the moment. Please try again later.", None

        # Store task as QUEUED
        with _tasks_lock:
            _tasks[task_id] = {
                'consumer_id': consumer_id,
                'docker_image': docker_image,
                'gpu_requirements': gpu_requirements,
                'provider_id': target_provider_id,
                'gpu_assigned': target_gpu_info,
                'status': 'QUEUED',
                'submission_time': datetime.now()
            }
            print(f"Task {task_id} queued for provider {target_provider_id} on GPU {target_gpu_info['id']}.")

        # Asynchronously dispatch the task to the selected Provider Agent
        # In a real system, you'd use a message queue or a background worker for this
        # to prevent blocking the Flask request. For MVP, direct call is fine.
        threading.Thread(target=_dispatch_task_to_provider, args=(
            task_id,
            docker_image,
            target_provider_id,
            _providers[target_provider_id]['address'],
            target_gpu_info['id']
        )).start()

        return True, f"Task {task_id} submitted and queued for execution.", task_id

def _dispatch_task_to_provider(task_id, docker_image, provider_id, provider_address, gpu_id):
    #Internal function to send the task execution command to the Provider Agent.
    #This runs in a separate thread.
    url = f"http://{provider_address}:5001/run_task" # Assuming agent runs on port 5001
    headers = {
        "Content-Type": "application/json",
        # For MVP, Provider Agent uses its own key to auth with Orchestrator,
        # but Orchestrator can call Agent directly if on private network.
        # For this MVP, let's assume direct call for simplicity.
        # If agent needs auth, you'd put a shared secret here.
    }
    payload = {
        "task_id": task_id,
        "docker_image": docker_image,
        "gpu_id": gpu_id
        # Later: add input_data_url, command_args, output_location, etc.
    }

    try:
        # Mark task as RUNNING as we attempt to dispatch
        with _tasks_lock:
            if task_id in _tasks:
                _tasks[task_id]['status'] = 'RUNNING'
                _tasks[task_id]['start_time'] = datetime.now()

        response = requests.post(url, headers=headers, json=payload, timeout=10) # Add timeout
        response.raise_for_status()
        print(f"Task {task_id} dispatched to provider {provider_id} successfully. Agent response: {response.json()}")
        # Agent will later send a status update for completion/failure
    except requests.exceptions.RequestException as e:
        print(f"Error dispatching task {task_id} to provider {provider_id}: {e}")
        with _tasks_lock:
            if task_id in _tasks:
                _tasks[task_id]['status'] = 'FAILED'
                _tasks[task_id]['error_message'] = str(e)
                _tasks[task_id]['end_time'] = datetime.now()

def update_task_status(task_id, status, details=None):
    #Called by Provider Agent to update task status.
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id]['status'] = status
            _tasks[task_id]['last_update'] = datetime.now()
            if status in ['COMPLETED', 'FAILED']:
                _tasks[task_id]['end_time'] = datetime.now()
            if details:
                _tasks[task_id].update(details)
            print(f"Task {task_id} status updated to {status}. Details: {details}")
            return True, "Task status updated."
        else:
            print(f"Attempted to update status for unknown task {task_id}.")
            return False, "Task not found."


def get_task_status(task_id):
    #Allows consumer or internal system to query task status.
    with _tasks_lock:
        return _tasks.get(task_id) # Returns task dict or None

# For MVP, we'll use an in-memory store.
# In Phase 2, this will be replaced with SQLite database interactions.
_providers = {} # Stores: {provider_id: {'gpus': [...], 'last_seen': datetime, 'address': 'IP'}}
_providers_lock = threading.Lock() # To protect _providers from concurrent access

def register_or_update_provider(provider_id, gpus, address):
    with _providers_lock:
        if provider_id in _providers:
            # Update existing provider
            _providers[provider_id]['gpus'] = gpus
            _providers[provider_id]['last_seen'] = datetime.now()
            _providers[provider_id]['address'] = address # Update address in case it changed
            print(f"Provider {provider_id} updated. GPUs: {gpus}")
            return True, f"Provider {provider_id} updated successfully."
        else:
            # Register new provider
            _providers[provider_id] = {
                'gpus': gpus,
                'last_seen': datetime.now(),
                'address': address,
                'status': 'active' # Initial status
            }
            print(f"Provider {provider_id} registered. GPUs: {gpus}")
            return True, f"Provider {provider_id} registered successfully."

def update_provider_heartbeat(provider_id, gpus=None):
    with _providers_lock:
        if provider_id in _providers:
            _providers[provider_id]['last_seen'] = datetime.now()
            if gpus is not None: # Allow optional GPU update during heartbeat
                _providers[provider_id]['gpus'] = gpus
            print(f"Heartbeat received from {provider_id}. Current providers: {len(_providers)}")
            return True, f"Heartbeat from {provider_id} received."
        else:
            print(f"Heartbeat from unknown provider {provider_id}.")
            return False, f"Provider {provider_id} not found. Please register first."

def get_available_gpus():
    #For debugging/testing: returns current known available GPUs across providers
    available = []
    with _providers_lock:
        for provider_id, info in _providers.items():
            # For MVP, we're assuming all reported GPUs are available
            # In later phases, we'll track 'used' GPUs.
            for gpu in info['gpus']:
                available.append({
                    'provider_id': provider_id,
                    'address': info['address'],
                    'gpu_info': gpu
                })
    return available

# You can add a simple endpoint to routes.py for testing this:
# @bp.route('/providers', methods=['GET'])
# def list_providers():
#     return jsonify(services.get_available_gpus())"""