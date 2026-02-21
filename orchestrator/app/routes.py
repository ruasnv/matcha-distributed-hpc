from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import jsonpickle
import uuid
import json
import os
import secrets
import boto3
from botocore.config import Config
from functools import wraps
from .models import db, Provider, Task, User, EnrollmentToken

bp = Blueprint('api', __name__, url_prefix='/')
LAST_CLEANUP_TIME = datetime.utcnow()

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

# --- Security Decorator ---
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        expected_key = os.getenv("ORCHESTRATOR_API_KEY", "debug-provider-key")
        if not api_key or api_key != expected_key:
            return jsonify({"error": "Unauthorized: Invalid or missing API Key"}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- Enrollment Logic ---

@bp.route('/auth/generate_enrollment_token', methods=['POST'])
def generate_token():
    data = request.get_json()
    clerk_id = data.get('clerk_id')
    
    if not clerk_id:
        return jsonify({"error": "Unauthorized"}), 401

    token_str = secrets.token_hex(3).upper() 
    
    new_token = EnrollmentToken(
        token=token_str, 
        user_id=clerk_id,
        expires_at=datetime.utcnow() + timedelta(minutes=15)
    )
    
    db.session.add(new_token)
    db.session.commit()
    
    return jsonify({"token": token_str}), 200


@bp.route('/provider/enroll', methods=['POST'])
def enroll_provider():
    data = request.json
    token_str = data.get('token', '').upper()
    provider_id = data.get('provider_id')
    
    # 👈 Fixed: Changed FALSE to False
    token_entry = EnrollmentToken.query.filter_by(token=token_str, is_used=False).first()
    
    if not token_entry or datetime.utcnow() > token_entry.expires_at:
        return jsonify({"error": "Invalid or expired token"}), 400
    
    token_entry.is_used = True
    db.session.commit()
    
    return jsonify({
        "user_id": token_entry.user_id,
        "message": "Enrollment successful"
    }), 200

@bp.route('/provider/my_devices', methods=['GET'])
def get_my_devices():
    clerk_id = request.args.get('clerk_id')
    
    if not clerk_id:
        print("DEBUG: Fetch failed because clerk_id was missing in the request")
        return jsonify({"error": "Unauthorized: No clerk_id provided"}), 401

    try:
        # Fetch devices linked to this Clerk ID
        devices = Provider.query.filter_by(user_id=clerk_id).all()
        
        return jsonify([{
            "id": d.id,
            "name": d.name,
            "status": d.status,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "telemetry": d.last_telemetry 
        } for d in devices]), 200
        
    except Exception as e:
        print(f"DEBUG: Database error in my_devices: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route('/consumer/upload_project', methods=['POST'])
def upload_project():
    try:
        file = request.files.get('file')
        clerk_id = request.form.get('clerk_id')
        
        if not file or not clerk_id:
            return jsonify({"error": "Missing file or user ID"}), 400

        file_name = f"{clerk_id}/{file.filename}"
        bucket = os.getenv('R2_BUCKET_NAME')
        
        # Upload to R2
        s3_client.upload_fileobj(
            file,
            bucket,
            file_name,
            ExtraArgs={'ContentType': file.content_type}
        )

        # Generate the public URL
        public_url = f"{os.getenv('R2_PUBLIC_DOMAIN')}/{file_name}"
        
        return jsonify({"project_url": public_url}), 200

    except Exception as e:
        print(f"R2 Upload Error: {str(e)}")
        return jsonify({"error": "Storage configuration error on server"}), 500

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
@require_api_key
def provider_register():
    data = request.get_json()
    provider_id = data.get('provider_id')
    
    # hardware_specs contains the dictionary from get_telemetry()
    specs = data.get('hardware_specs', {}) 
    
    # IMPORTANT: The agent now sends a list of GPUs separately
    # We should prioritize that list if it exists
    detected_gpus = data.get('gpus', [])
    
    # Fallback: if 'gpus' is empty, try to extract from 'specs' (legacy/telemetry)
    if not detected_gpus and "gpu" in specs and specs["gpu"]:
        detected_gpus = [{"id": "gpu-0", "name": specs["gpu"]["name"], "status": "idle"}]

    provider = Provider.query.get(provider_id)
    
    if provider:
        provider.specs = specs
        # We store the list as a JSON string for the matching logic
        provider.gpus = jsonpickle.encode(detected_gpus, unpicklable=False)
        provider.user_id = data.get('user_id') # Update user_id just in case
        provider.last_seen = datetime.utcnow()
        provider.status = 'active'
    else:
        provider = Provider(
            id=provider_id,
            name=provider_id,
            user_id=data.get('user_id'),
            specs=specs,
            gpus=jsonpickle.encode(detected_gpus, unpicklable=False),
            last_seen=datetime.utcnow(),
            status='active'
        )
        db.session.add(provider)
    
    try:
        db.session.commit()
        return jsonify({"message": "Successfully registered"}), 200
    except Exception as e:
        db.session.rollback()
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
    # Check if result_url was sent in the 'details' dict
    if 'result_url' in details:
        task.result_url = details['result_url']
        print(f"DEBUG: Received Result URL for task {task_id}") # Add this to debug!
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
    clerk_id = data.get('clerk_id') # Use clerk_id consistently
    
    if not clerk_id:
        return jsonify({"error": "User authentication required"}), 401

    task_id = str(uuid.uuid4())
    new_task = Task(
        id=task_id,
        user_id=clerk_id, # Link task to the authenticated user
        docker_image=data.get('docker_image', 'matcha-runner:latest'),
        status='QUEUED',
        submission_time=datetime.utcnow(),
        input_path=data.get('input_path'), # This is the Presigned R2 URL
        script_path=data.get('script_path', 'main.py'),
        env_vars=json.dumps(data.get('env_vars', {})) 
    )
    
    db.session.add(new_task)
    db.session.commit()
    return jsonify({"task_id": task_id, "message": "Task submitted."}), 200

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

@bp.route('/consumer/tasks', methods=['GET'])
def get_user_tasks():
    global LAST_CLEANUP_TIME
    clerk_id = request.args.get('clerk_id')
    
    if not clerk_id:
        return jsonify({"error": "Unauthorized"}), 401

    # 1. OPTIMIZED CLEANUP: Only run if it's been more than 5 minutes
    now = datetime.utcnow()
    if (now - LAST_CLEANUP_TIME).total_seconds() > 300: # 300 seconds = 5 minutes
        stale_limit = now - timedelta(minutes=10)
        
        # Only cleanup tasks that are stuck in 'RUNNING'
        stuck_tasks = Task.query.filter(
            Task.status == 'RUNNING',
            Task.last_update < stale_limit
        ).all()

        for task in stuck_tasks:
            task.status = 'FAILED'
            task.error_message = "Task timed out: Provider heartbeat lost."
            # If the task had a provider, we should ideally free that GPU too
        
        if stuck_tasks:
            try:
                db.session.commit()
                print(f"🧹 Cleaned up {len(stuck_tasks)} stuck tasks.")
            except Exception as e:
                db.session.rollback()
                print(f"Cleanup error: {e}")
        
        LAST_CLEANUP_TIME = now # Reset the timer

    # 2. FAST FETCH: Just get the user's tasks
    user_tasks = Task.query.filter_by(user_id=clerk_id).order_by(Task.submission_time.desc()).all()
    
    return jsonify([{
        "id": t.id,
        "status": t.status,
        "stdout": t.stdout,
        "result_url": t.result_url,
        "submission_time": t.submission_time.isoformat() if t.submission_time else None
    } for t in user_tasks]), 200

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

@bp.route('/provider/heartbeat', methods=['POST'])
@require_api_key 
def provider_heartbeat():
    data = request.get_json()
    provider_id = data.get('provider_id')
    telemetry = data.get('telemetry')
    
    if not provider_id:
        return jsonify({"error": "Missing provider_id"}), 400

    provider = Provider.query.get(provider_id)
    if provider:
        provider.last_seen = datetime.utcnow()
        # Ensure 'last_telemetry' exists in your models.py as a JSON column!
        provider.last_telemetry = telemetry 
        db.session.commit()
        return jsonify({"status": "received"}), 200
    
    return jsonify({"error": "Provider not found"}), 404

@bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"}), 200