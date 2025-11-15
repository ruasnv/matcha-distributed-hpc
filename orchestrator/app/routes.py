from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import jsonpickle
import uuid
import json

from .models import db, Provider, Task

bp = Blueprint('api', __name__, url_prefix='/')

# --- Provider Management ---

@bp.route('/provider/register', methods=['POST'])
def provider_register():
    data = request.get_json()
    provider_id = data.get('provider_id')
    gpus = data.get('gpus')
    
    if not provider_id or not gpus:
        return jsonify({"error": "Missing provider_id or gpus data"}), 400

    gpus_json = jsonpickle.encode(gpus, unpicklable=False)
    provider = Provider.query.get(provider_id)
    
    if provider:
        provider.gpus = gpus_json
        provider.last_seen = datetime.utcnow()
        provider.status = 'active'
        message = f"Provider {provider_id} re-registered successfully."
    else:
        provider = Provider(
            id=provider_id,
            name=provider_id,
            gpus=gpus_json,
            address="N/A (Pull Model)", # We no longer need the provider's address
            last_seen=datetime.utcnow(),
            status='active'
        )
        db.session.add(provider)
        message = f"Provider {provider_id} registered successfully."
    
    try:
        db.session.commit()
        print(f"DB: {message} GPUs: {gpus}")
        return jsonify({"message": message}), 200
    except Exception as e:
        db.session.rollback()
        print(f"DB Error registering/updating provider {provider_id}: {e}")
        return False, f"Database error: {e}"

@bp.route('/provider/task_update', methods=['POST'])
def agent_task_update():
    data = request.get_json()
    task_id = data.get('task_id')
    status = data.get('status')
    details = data.get('details', {})

    if not task_id or not status:
        return jsonify({"error": "Missing task_id or status"}), 400

    task = Task.query.get(task_id)
    if not task:
        return jsonify({"error": "Task not found."}), 404

    # Update task details
    task.status = status
    task.last_update = datetime.utcnow()
    if 'stdout' in details:
        task.stdout = details['stdout']
    if 'stderr' in details:
        task.stderr = details['stderr']
    if status in ['COMPLETED', 'FAILED', 'CANCELLED']:
        task.end_time = datetime.utcnow()
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"DB error updating task: {e}"}), 500

    # If task is finished, free the GPU
    if status in ['COMPLETED', 'FAILED', 'CANCELLED']:
        if task.provider_id and task.gpu_assigned:
            provider = Provider.query.get(task.provider_id)
            gpu_assigned_id = jsonpickle.decode(task.gpu_assigned)['id']
            if provider:
                provider_gpus = jsonpickle.decode(provider.gpus)
                gpu_freed = False
                for i, gpu in enumerate(provider_gpus):
                    if gpu['id'] == gpu_assigned_id:
                        provider_gpus[i]['status'] = 'idle'
                        gpu_freed = True
                        break
                if gpu_freed:
                    provider.gpus = jsonpickle.encode(provider_gpus, unpicklable=False)
                    db.session.commit()
                    print(f"Provider {task.provider_id} GPU {gpu_assigned_id} has been freed.")
    
    return jsonify({"message": "Task status updated."}), 200

# --- Consumer Management ---

@bp.route('/consumer/submit_task', methods=['POST'])
def consumer_submit_task():
    data = request.get_json()
    docker_image = data.get('docker_image')
    if not docker_image:
        return jsonify({"error": "Missing required field: docker_image"}), 400

    task_id = str(uuid.uuid4())
    new_task = Task(
        id=task_id,
        consumer_id=data.get('consumer_id', 'default_consumer'),
        docker_image=docker_image,
        gpu_requirements=jsonpickle.encode(data.get('gpu_requirements', {})),
        status='QUEUED', # Task is now just queued
        submission_time=datetime.utcnow(),
        # --- ADD THESE NEW FIELDS ---
        input_path=data.get('input_path'),
        output_path=data.get('output_path'),
        script_path=data.get('script_path'),
        # We'll just pass the env_vars dict as a JSON string
        env_vars=json.dumps(data.get('env_vars', {})) 
    )
    
    try:
        db.session.add(new_task)
        db.session.commit()
        return jsonify({"task_id": task_id, "message": f"Task {task_id} submitted and queued."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"DB error queuing task: {e}"}), 503

@bp.route('/consumer/task_status/<task_id>', methods=['GET'])
def consumer_task_status(task_id):
    task = Task.query.get(task_id)
    if task:
        task_dict = {
            'id': task.id, 'consumer_id': task.consumer_id,
            'docker_image': task.docker_image,
            'gpu_requirements': jsonpickle.decode(task.gpu_requirements),
            'provider_id': task.provider_id,
            'gpu_assigned': jsonpickle.decode(task.gpu_assigned) if task.gpu_assigned else None,
            'status': task.status,
            'submission_time': task.submission_time,
            'last_update': task.last_update,
            'start_time': task.start_time, 'end_time': task.end_time,
            'error_message': task.error_message, 'stdout': task.stdout,
            'stderr': task.stderr
        }
        return jsonify(task_dict), 200
    else:
        return jsonify({"error": f"Task ID {task_id} not found."}), 404

# --- NEW ENDPOINT FOR PROVIDERS ---

@bp.route('/provider/get_task', methods=['POST'])
def provider_get_task():
    data = request.get_json()
    provider_id = data.get('provider_id')
    if not provider_id:
        return jsonify({"error": "Missing provider_id"}), 400

    provider = Provider.query.get(provider_id)
    if not provider:
        return jsonify({"error": "Provider not registered."}), 404

    # 1. Update heartbeat for this provider
    provider.last_seen = datetime.utcnow()
    provider.status = 'active'
    
    # 2. Find an idle GPU on this provider
    provider_gpus = jsonpickle.decode(provider.gpus)
    idle_gpu = None
    idle_gpu_index = -1
    for i, gpu in enumerate(provider_gpus):
        if gpu.get('status', 'idle') == 'idle':
            idle_gpu = gpu
            idle_gpu_index = i
            break
    
    # If no idle GPUs on this provider, just return
    if not idle_gpu:
        db.session.commit()
        return jsonify({"task": None, "message": "Heartbeat received. No idle GPUs."}), 200

    # 3. Find a queued task
    task = Task.query.filter_by(status='QUEUED').order_by(Task.submission_time).first()
    
    # If no queued tasks, just return
    if not task:
        db.session.commit()
        return jsonify({"task": None, "message": "Heartbeat received. No queued tasks."}), 200

    # 4. WE HAVE A MATCH! Assign task to provider's GPU
    task.provider_id = provider_id
    task.gpu_assigned = jsonpickle.encode(idle_gpu, unpicklable=False)
    task.status = 'RUNNING'
    task.start_time = datetime.utcnow()
    
    # Mark the GPU as busy
    provider_gpus[idle_gpu_index]['status'] = 'busy'
    provider.gpus = jsonpickle.encode(provider_gpus, unpicklable=False)
    
    try:
        db.session.commit()
        print(f"Task {task.id} assigned to provider {provider_id} on GPU {idle_gpu['id']}")
        # Return the task to the provider
        return jsonify({
            "task": {
                "task_id": task.id,
                "docker_image": task.docker_image,
                "gpu_id": idle_gpu['id'],

                # --- ADD THESE NEW FIELDS ---
                "input_path": task.input_path,
                "output_path": task.output_path,
                "script_path": task.script_path,
                "env_vars": json.loads(task.env_vars) if task.env_vars else {}
            },
            "message": "Task assigned."
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"DB error assigning task: {e}"}), 500


# --- Other Endpoints (Health, Debug) ---

@bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"}), 200

# (Your debug routes can stay here if you want)