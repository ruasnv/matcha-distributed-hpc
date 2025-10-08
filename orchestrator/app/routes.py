from flask import Blueprint, request, jsonify, current_app, g
from datetime import datetime
from . import get_db, init_db # Import database functions from __init__.py
import threading
import jsonpickle
import uuid
import requests
import json
import sqlite3
import click

# Define the Blueprint for all API routes
bp = Blueprint('api', __name__, url_prefix='/')

# --- Helper Functions (Your provided service logic using SQLite) ---

def register_or_update_provider(provider_id, gpus, address):
    # This function is correct as long as the 'address' passed in is the Docker service name.
    db = get_db()
    cursor = db.cursor()
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
                (provider_id, provider_id, gpus_json, address) 
            )
            message = f"Provider {provider_id} registered successfully."
        else:
            message = f"Provider {provider_id} updated successfully."
        
        db.commit()
        print(f"DB: {message} Stored Address: {address}. GPUs: {gpus}")
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

def update_task_status(task_id, status, details=None):
    db = get_db()
    cursor = db.cursor()
    
    update_fields = ["status = ?", "last_update = CURRENT_TIMESTAMP"]
    update_params = [status]
    
    # Intelligently handle the details dictionary
    if details:
        if 'start_time' in details:
            update_fields.append("start_time = ?")
            update_params.append(details['start_time'])
        if 'stdout' in details:
            update_fields.append("stdout = ?")
            update_params.append(details['stdout'])
        if 'stderr' in details:
            update_fields.append("stderr = ?")
            update_params.append(details['stderr'])
        
        # Store any other miscellaneous details in the error_message field
        other_details = {k: v for k, v in details.items() if k not in ['start_time', 'stdout', 'stderr']}
        if other_details:
            update_fields.append("error_message = ?")
            update_params.append(json.dumps(other_details))

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


def schedule_task(consumer_id, docker_image, gpu_requirements):
    db = get_db()
    cursor = db.cursor()
    task_id = str(uuid.uuid4())

    gpu_requirements_json = jsonpickle.encode(gpu_requirements, unpicklable=False)

    target_provider_id = None
    target_gpu_info = None

    providers_info = get_all_providers()
    for provider_info in providers_info:
        # Simple scheduling: find the first active provider
        if provider_info['status'] == 'active' and provider_info['gpus']:
            target_provider_id = provider_info['id']
            target_gpu_info = provider_info['gpus'][0]
            break

    if not target_provider_id:
        return False, "No available GPUs at the moment. Please try again later.", None

    provider_address = get_provider(target_provider_id)['address'] # This should now be 'provider'
    gpu_assigned_json = jsonpickle.encode(target_gpu_info, unpicklable=False)

    try:
        cursor.execute(
            """INSERT INTO tasks (id, consumer_id, docker_image, gpu_requirements, provider_id, gpu_assigned, status, submission_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (task_id, consumer_id, docker_image, gpu_requirements_json, target_provider_id, gpu_assigned_json, 'QUEUED')
        )
        db.commit()
        print(f"DB: Task {task_id} queued for provider {target_provider_id} on GPU {target_gpu_info['id']}.")

        # Dispatch the task in a separate thread
        threading.Thread(target=_dispatch_task_to_provider, args=(
            current_app._get_current_object(), # Pass the app instance
            task_id,
            docker_image,
            target_provider_id,
            provider_address, # This is the Docker service name ('provider')
            target_gpu_info['id']
        )).start()

        return True, f"Task {task_id} submitted and queued for execution.", task_id
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error scheduling task {task_id}: {e}")
        return False, f"Database error: {e}", None


def _dispatch_task_to_provider(app, task_id, docker_image, provider_id, provider_address, gpu_id):
    """
    Internal function to send the task execution command to the Provider Agent.
    This runs in a separate thread and pushes an application context to handle DB access.
    """
    with app.app_context():
        # This URL is now correctly formed using the stored service name
        url = f"http://{provider_address}:5001/run_task" 
        headers = {"Content-Type": "application/json"}
        payload = {
            "task_id": task_id,
            "docker_image": docker_image,
            "gpu_id": gpu_id
        }

         # Update task status to RUNNING, ensuring the timestamp format is DB-friendly
        start_time_str = datetime.now().isoformat(sep=' ', timespec='microseconds')
        update_task_status(task_id, 'RUNNING', {'start_time': start_time_str})

        try:
            # We use the correct hostname 'provider', which Docker resolves internally
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            response.raise_for_status()
            print(f"Task {task_id} dispatched to provider {provider_id} successfully. Agent response: {response.json()}")
        except requests.exceptions.RequestException as e:
            print(f"Error dispatching task {task_id} to provider {provider_id}: {e}")
            error_details = {"error_message": str(e)}
            if e.response is not None:
                error_details["stderr"] = e.response.text
            
            # The original error (Connection refused) is now caught and recorded here
            update_task_status(task_id, 'FAILED', error_details)

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
        
        # Try to parse error_message back into a dictionary if it contains JSON
        if task_dict['error_message']:
            try:
                task_dict['error_message'] = json.loads(task_dict['error_message'])
            except (json.JSONDecodeError, TypeError):
                pass
        
        return task_dict
    return None

# --- API Route Definitions ---

# PROVIDER ENDPOINTS
@bp.route('/provider/register', methods=['POST'])
def provider_register():
    data = request.get_json()
    provider_id = data.get('provider_id')
    gpus = data.get('gpus')

    if not provider_id or not gpus:
        return jsonify({"error": "Missing provider_id or gpus data"}), 400

    # *** CRITICAL FIX APPLIED HERE ***
    # In a Docker Compose network, containers use the service name as the hostname.
    # We must explicitly store the service name, NOT the remote IP.
    provider_internal_address = "provider" 

    success, message = register_or_update_provider(provider_id, gpus, provider_internal_address)
    
    if success:
        return jsonify({"message": message}), 200
    else:
        return jsonify({"error": message}), 500

@bp.route('/provider/heartbeat', methods=['POST'])
def provider_heartbeat():
    data = request.get_json()
    provider_id = data.get('provider_id')
    gpus = data.get('gpus') # Optional update to GPUs during heartbeat

    if not provider_id:
        return jsonify({"error": "Missing provider_id"}), 400

    success, message = update_provider_heartbeat(provider_id, gpus)

    if success:
        return jsonify({"message": message}), 200
    else:
        # Return 404 if provider isn't registered, instructing the provider to register
        return jsonify({"error": message}), 404


# CONSUMER ENDPOINTS
@bp.route('/consumer/submit_task', methods=['POST'])
def consumer_submit_task():
    data = request.get_json()
    consumer_id = data.get('consumer_id', 'default_consumer') # Default ID for CLI
    docker_image = data.get('docker_image')
    gpu_requirements = data.get('gpu_requirements', {})

    if not docker_image:
        return jsonify({"error": "Missing required field: docker_image"}), 400

    success, message, task_id = schedule_task(consumer_id, docker_image, gpu_requirements)
    
    if success:
        return jsonify({"task_id": task_id, "message": message}), 200
    else:
        return jsonify({"error": message}), 503 # Service Unavailable

@bp.route('/consumer/task_status/<task_id>', methods=['GET'])
def consumer_task_status(task_id):
    task_info = get_task_status(task_id)
    if task_info:
        return jsonify(task_info), 200
    else:
        return jsonify({"error": f"Task ID {task_id} not found."}), 404

# AGENT CALLBACK ENDPOINT (for Provider Agent to report job completion/failure)
@bp.route('/provider/task_update', methods=['POST'])
def agent_task_update():
    data = request.get_json()
    task_id = data.get('task_id')
    status = data.get('status')
    details = data.get('details', {}) # Should contain stdout/stderr/exit_code

    if not task_id or not status:
        return jsonify({"error": "Missing task_id or status"}), 400
    
    if status not in ['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED']:
         return jsonify({"error": f"Invalid status: {status}"}), 400

    success, message = update_task_status(task_id, status, details)

    if success:
        return jsonify({"message": message}), 200
    else:
        return jsonify({"error": message}), 404 # Task not found

# --- DEBUG ENDPOINTS (Only visible when FLASK_ENV is 'development') ---

@bp.route('/debug/providers', methods=['GET'])
def get_all_providers_debug():
    if current_app.config['FLASK_ENV'] != 'development':
        return jsonify({"error": "Debug endpoint restricted to development environment"}), 404
    
    providers = get_all_providers()
    return jsonify(providers), 200

@bp.route('/debug/tasks', methods=['GET'])
def get_all_tasks_debug():
    if current_app.config['FLASK_ENV'] != 'development':
        return jsonify({"error": "Debug endpoint restricted to development environment"}), 404
    
    db = get_db()
    task_rows = db.execute('SELECT * FROM tasks ORDER BY submission_time DESC').fetchall()
    tasks_list = []
    for row in task_rows:
        task_dict = dict(row)
        # Deserialize JSON fields before outputting
        if task_dict.get('gpu_requirements'):
            task_dict['gpu_requirements'] = jsonpickle.decode(task_dict['gpu_requirements'])
        if task_dict.get('gpu_assigned'):
            task_dict['gpu_assigned'] = jsonpickle.decode(task_dict['gpu_assigned'])
        tasks_list.append(task_dict)
        
    return jsonify(tasks_list), 200

# Add a CLI command definition to the Blueprint (used by app.cli)
@bp.cli.command('init-db')
def init_db_command():
    init_db()
    click.echo('Initialized the database.')

@bp.route('/health', methods=['GET'])
def health_check():
    """A simple health check endpoint that doesn't require an API key."""
    return jsonify({"status": "ok"}), 200
