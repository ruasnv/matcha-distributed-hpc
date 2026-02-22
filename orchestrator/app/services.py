#services.py
from datetime import datetime
from flask import current_app, g
from . import get_db
import threading
import jsonpickle
import uuid
import threading
import requests
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