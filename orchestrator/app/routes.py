from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import jsonpickle
import uuid
import json
from .models import db, Provider, Task, User
import os
import boto3
from botocore.config import Config

bp = Blueprint('api', __name__, url_prefix='/')

# Initialize the R2 client
# Use 'auto' for region_name as R2 doesn't use standard AWS regions
s3_client = boto3.client(
    's3',
    endpoint_url=os.getenv('R2_ENDPOINT_URL'),
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
    config=Config(signature_version='s3v4'),
    region_name='auto'
)

@bp.route('/consumer/upload_project', methods=['POST'])
def upload_project():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Generate a unique path: projects/<uuid>.zip
    project_id = str(uuid.uuid4())
    filename = f"projects/{project_id}.zip"

    try:
        s3_client.upload_fileobj(
            file, 
            os.getenv('R2_BUCKET_NAME'), 
            filename
        )
        # Return the R2 key so the database can store it
        return jsonify({"project_url": f"r2://{filename}"}), 200
    except Exception as e:
        print(f"R2 Upload Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- Auth Management ---

@bp.route('/auth/sync', methods=['POST']) # Use @bp.route and add 'methods' (plural)
def sync_user():
    data = request.json
    clerk_id = data.get('clerk_id')
    email = data.get('email')

    if not clerk_id or not email:
        return jsonify({"error": "Missing data"}), 400

    # Upsert logic
    user = User.query.get(clerk_id)
    if not user:
        user = User(id=clerk_id, email=email)
        db.session.add(user)
    else:
        user.email = email
    
    try:
        db.session.commit()
        return jsonify({"message": "User synced", "user_id": user.id}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database error: {e}"}), 500

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
        user_id=data.get('user_id'), # This will be None, which is now allowed
        gpus=gpus_json,
        address="N/A (Pull Model)",
        last_seen=datetime.utcnow(),
        status='active'
    )
    
    try:
        db.session.add(provider)
        db.session.commit()
        return jsonify({"message": "Successfully registered"}), 200
    except Exception as e:
        db.session.rollback()
        # --- FIX THIS RETURN LINE ---
        return jsonify({"error": f"Database error: {str(e)}"}), 500

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
        # Synchronized: Changed consumer_id to user_id to match Model
        user_id=data.get('user_id') or data.get('consumer_id', 'default_user'),
        docker_image=docker_image,
        gpu_requirements=jsonpickle.encode(data.get('gpu_requirements', {})),
        status='QUEUED',
        submission_time=datetime.utcnow(),
        input_path=data.get('input_path'),
        output_path=data.get('output_path'),
        script_path=data.get('script_path'),
        env_vars=json.dumps(data.get('env_vars', {})) 
    )
    
    try:
        db.session.add(new_task)
        db.session.commit()
        return jsonify({"task_id": task_id, "message": f"Task {task_id} submitted."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"DB error: {e}"}), 503

@bp.route('/consumer/task_status/<task_id>', methods=['GET'])
def consumer_task_status(task_id):
    task = Task.query.get(task_id)
    if task:
        return jsonify({
            'id': task.id, 
            'user_id': task.user_id,
            'status': task.status,
            'docker_image': task.docker_image,
            'submission_time': task.submission_time,
            'stdout': task.stdout,
            'stderr': task.stderr,
            'error_message': task.error_message,
            'provider_id': task.provider_id
        }), 200
    return jsonify({"error": "Task not found"}), 404

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
@bp.route('/consumer/tasks/debug', methods=['GET'])
def get_all_tasks_debug():
    tasks = Task.query.order_by(Task.submission_time.desc()).all()
    return jsonify([{
        'id': t.id,
        'status': t.status,
        'submission_time': t.submission_time.isoformat() if t.submission_time else None,
        'provider_id': t.provider_id
    } for t in tasks]), 201

@bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"}), 200