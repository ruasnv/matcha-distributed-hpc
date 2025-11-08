from flask import Blueprint, request, jsonify, current_app, g
from datetime import datetime
import threading
import jsonpickle
import uuid
import requests
import json

# Import our new DB session and models
from .models import db, Provider, Task

bp = Blueprint('api', __name__, url_prefix='/')

# --- Helper Functions (Now with SQLAlchemy!) ---

def register_or_update_provider(provider_id, gpus, address):
    gpus_json = jsonpickle.encode(gpus, unpicklable=False)

    provider = Provider.query.get(provider_id)
    if provider:
        # Update existing provider
        provider.gpus = gpus_json
        provider.address = address
        provider.last_seen = datetime.utcnow()
        provider.status = 'active'
        message = f"Provider {provider_id} updated successfully."
    else:
        # Insert new provider
        provider = Provider(
            id=provider_id,
            name=provider_id,
            gpus=gpus_json,
            address=address,
            last_seen=datetime.utcnow(),
            status='active'
        )
        db.session.add(provider)
        message = f"Provider {provider_id} registered successfully."

    try:
        db.session.commit()
        print(f"DB: {message} Stored Address: {address}. GPUs: {gpus}")
        return True, message
    except Exception as e:
        db.session.rollback()
        print(f"DB Error registering/updating provider {provider_id}: {e}")
        return False, f"Database error: {e}"

def update_provider_heartbeat(provider_id, gpus=None):
    provider = Provider.query.get(provider_id)
    if not provider:
        return False, f"Provider {provider_id} not found. Please register first."

    provider.last_seen = datetime.utcnow()
    provider.status = 'active'
    if gpus is not None:
        provider.gpus = jsonpickle.encode(gpus, unpicklable=False)

    try:
        db.session.commit()
        print(f"DB: Heartbeat from {provider_id} received.")
        return True, f"Heartbeat from {provider_id} received."
    except Exception as e:
        db.session.rollback()
        print(f"DB Error updating heartbeat for {provider_id}: {e}")
        return False, f"Database error: {e}"

def get_provider(provider_id):
    provider = Provider.query.get(provider_id)
    if provider:
        provider_dict = {
            'id': provider.id, 'name': provider.name,
            'gpus': jsonpickle.decode(provider.gpus),
            'address': provider.address, 'last_seen': provider.last_seen,
            'status': provider.status
        }
        return provider_dict
    return None

def get_all_providers():
    providers = Provider.query.all()
    providers_list = []
    for provider in providers:
        providers_list.append({
            'id': provider.id, 'name': provider.name,
            'gpus': jsonpickle.decode(provider.gpus),
            'address': provider.address, 'last_seen': provider.last_seen,
            'status': provider.status
        })
    return providers_list

def update_task_status(task_id, status, details=None):
    task = Task.query.get(task_id)
    if not task:
        return False, "Task not found."

    task.status = status
    task.last_update = datetime.utcnow()

    if details:
        if 'start_time' in details:
            task.start_time = details['start_time']
        if 'stdout' in details:
            task.stdout = details['stdout']
        if 'stderr' in details:
            task.stderr = details['stderr']

        other_details = {k: v for k, v in details.items() if k not in ['start_time', 'stdout', 'stderr']}
        if other_details:
            task.error_message = json.dumps(other_details)

    if status in ['COMPLETED', 'FAILED', 'CANCELLED']:
        task.end_time = datetime.utcnow()

    try:
        db.session.commit()
        print(f"DB: Task {task_id} status updated to {status}.")
        return True, "Task status updated."
    except Exception as e:
        db.session.rollback()
        print(f"DB Error updating task {task_id} status: {e}")
        return False, f"Database error: {e}"

def schedule_task(consumer_id, docker_image, gpu_requirements):
    task_id = str(uuid.uuid4())
    gpu_requirements_json = jsonpickle.encode(gpu_requirements, unpicklable=False)

    target_provider = None
    target_gpu_info = None
    provider_to_update = None

    providers = get_all_providers() # This now returns dicts
    for provider in providers:
        if provider['status'] == 'active':
            provider_gpus = provider['gpus'] # This is a list of dicts
            for i, gpu in enumerate(provider_gpus):
                if gpu.get('status', 'idle') == 'idle':
                    target_provider = provider

                    provider_gpus[i]['status'] = 'busy'
                    target_gpu_info = provider_gpus[i]

                    # Get the provider object to update
                    provider_to_update = Provider.query.get(provider['id'])
                    provider_to_update.gpus = jsonpickle.encode(provider_gpus, unpicklable=False)
                    break
            if target_provider:
                break

    if not target_provider:
        return False, "No available GPUs at the moment. Please try again later.", None

    provider_address = target_provider['address']
    gpu_assigned_json = jsonpickle.encode(target_gpu_info, unpicklable=False)

    new_task = Task(
        id=task_id,
        consumer_id=consumer_id,
        docker_image=docker_image,
        gpu_requirements=gpu_requirements_json,
        provider_id=target_provider['id'],
        gpu_assigned=gpu_assigned_json,
        status='QUEUED',
        submission_time=datetime.utcnow()
    )

    try:
        db.session.add(new_task)
        db.session.add(provider_to_update) # Add updated provider
        db.session.commit()
        print(f"DB: Task {task_id} queued for provider {target_provider['id']} on GPU {target_gpu_info['id']}.")

        threading.Thread(target=_dispatch_task_to_provider, args=(
            current_app._get_current_object(),
            task_id, docker_image, target_provider['id'],
            provider_address, target_gpu_info['id']
        )).start()

        return True, f"Task {task_id} submitted and assigned to GPU {target_gpu_info['id']}.", task_id
    except Exception as e:
        db.session.rollback()
        print(f"DB Error scheduling task {task_id}: {e}")
        return False, f"Database error: {e}", None

def _dispatch_task_to_provider(app, task_id, docker_image, provider_id, provider_address, gpu_id):
    with app.app_context():
        url = f"http://{provider_address}:5001/run_task" 
        headers = {"Content-Type": "application/json"}
        payload = { "task_id": task_id, "docker_image": docker_image, "gpu_id": gpu_id }

        start_time_str = datetime.utcnow().isoformat(sep=' ', timespec='microseconds')
        update_task_status(task_id, 'RUNNING', {'start_time': start_time_str})

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            response.raise_for_status()
            print(f"Task {task_id} dispatched to provider {provider_id} successfully. Agent response: {response.json()}")
        except requests.exceptions.RequestException as e:
            print(f"Error dispatching task {task_id} to provider {provider_id}: {e}")
            error_details = {"error_message": str(e)}
            if e.response is not None:
                error_details["stderr"] = e.response.text
            update_task_status(task_id, 'FAILED', error_details)

def get_task_status(task_id):
    task = Task.query.get(task_id)
    if task:
        task_dict = {
            'id': task.id, 'consumer_id': task.consumer_id,
            'docker_image': task.docker_image,
            'gpu_requirements': jsonpickle.decode(task.gpu_requirements),
            'provider_id': task.provider_id,
            'gpu_assigned': jsonpickle.decode(task.gpu_assigned),
            'status': task.status,
            'submission_time': task.submission_time,
            'last_update': task.last_update,
            'start_time': task.start_time, 'end_time': task.end_time,
            'error_message': task.error_message, 'stdout': task.stdout,
            'stderr': task.stderr
        }
        return task_dict
    return None

# --- API Route Definitions (Unchanged from here) ---

@bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"}), 200

# PROVIDER ENDPOINTS
@bp.route('/provider/register', methods=['POST'])
def provider_register():
    data = request.get_json()
    provider_id = data.get('provider_id')
    gpus = data.get('gpus')
    if not provider_id or not gpus:
        return jsonify({"error": "Missing provider_id or gpus data"}), 400
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
    gpus = data.get('gpus')
    if not provider_id:
        return jsonify({"error": "Missing provider_id"}), 400
    success, message = update_provider_heartbeat(provider_id, gpus)
    if success:
        return jsonify({"message": message}), 200
    else:
        return jsonify({"error": message}), 404

@bp.route('/provider/task_update', methods=['POST'])
def agent_task_update():
    data = request.get_json()
    task_id = data.get('task_id')
    status = data.get('status')
    details = data.get('details', {})

    if not task_id or not status:
        return jsonify({"error": "Missing task_id or status"}), 400

    success, message = update_task_status(task_id, status, details)
    if not success:
        return jsonify({"error": message}), 404

    # If task is finished, free the GPU
    if status in ['COMPLETED', 'FAILED', 'CANCELLED']:
        task_info = get_task_status(task_id)
        if task_info and task_info.get('provider_id') and task_info.get('gpu_assigned'):
            provider_id = task_info['provider_id']
            gpu_assigned_id = task_info['gpu_assigned']['id']

            provider = get_provider(provider_id)
            if provider:
                provider_gpus = provider['gpus']
                gpu_freed = False
                for i, gpu in enumerate(provider_gpus):
                    if gpu['id'] == gpu_assigned_id:
                        provider_gpus[i]['status'] = 'idle'
                        gpu_freed = True
                        break

                if gpu_freed:
                    provider_obj = Provider.query.get(provider_id)
                    provider_obj.gpus = jsonpickle.encode(provider_gpus, unpicklable=False)
                    db.session.commit()
                    print(f"Provider {provider_id} GPU {gpu_assigned_id} has been freed.")

    return jsonify({"message": "Task status updated and resource status handled."}), 200

# CONSUMER ENDPOINTS
@bp.route('/consumer/submit_task', methods=['POST'])
def consumer_submit_task():
    data = request.get_json()
    consumer_id = data.get('consumer_id', 'default_consumer')
    docker_image = data.get('docker_image')
    gpu_requirements = data.get('gpu_requirements', {})

    if not docker_image:
        return jsonify({"error": "Missing required field: docker_image"}), 400

    success, message, task_id = schedule_task(consumer_id, docker_image, gpu_requirements)

    if success:
        return jsonify({"task_id": task_id, "message": message}), 200
    else:
        return jsonify({"error": message}), 503

@bp.route('/consumer/task_status/<task_id>', methods=['GET'])
def consumer_task_status(task_id):
    task_info = get_task_status(task_id)
    if task_info:
        return jsonify(task_info), 200
    else:
        return jsonify({"error": f"Task ID {task_id} not found."}), 404

# DEBUG ENDPOINTS
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

    tasks = Task.query.order_by(Task.submission_time.desc()).all()
    tasks_list = []
    for task in tasks:
        tasks_list.append({
            'id': task.id, 'status': task.status,
            'docker_image': task.docker_image,
            'provider_id': task.provider_id,
            'submission_time': task.submission_time
        })
    return jsonify(tasks_list), 200