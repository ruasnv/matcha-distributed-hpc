from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import uuid
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(128), primary_key=True) # Clerk ID
    email = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tasks = db.relationship('Task', backref='owner', lazy=True)
    providers = db.relationship('Provider', backref='owner', lazy=True)

class Provider(db.Model):
    __tablename__ = 'providers'
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.String(128), db.ForeignKey('users.id'), nullable=True)
    gpus = db.Column(db.Text) # JSON string of GPU resources
    status = db.Column(db.String(20), default='active')
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    address = db.Column(db.String(255), nullable=True)
    last_telemetry = db.Column(db.JSON, nullable=True)
    specs = db.Column(db.JSON)

class EnrollmentToken(db.Model):
    __tablename__ = 'enrollment_tokens'
    token = db.Column(db.String, primary_key=True)
    user_id = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)

class Task(db.Model):
    __tablename__ = 'tasks'
    
    # Identity & Ownership
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(128), db.ForeignKey('users.id'), nullable=True)
    provider_id = db.Column(db.String(36), db.ForeignKey('providers.id'), nullable=True)
    
    # Execution State
    status = db.Column(db.String(20), default='QUEUED')
    docker_image = db.Column(db.String(255))
    gpu_requirements = db.Column(db.Text)
    gpu_assigned = db.Column(db.Text)
    
    # Workflow Metadata
    input_path = db.Column(db.Text)   # Presigned URL for code
    output_path = db.Column(db.Text)  # Target path if applicable
    script_path = db.Column(db.Text)  # Entry point (e.g. main.py)
    env_vars = db.Column(db.Text)     # JSON string of env variables
    result_url = db.Column(db.Text)   # Artifacts download link (R2)
    
    # Time Tracking
    submission_time = db.Column(db.DateTime, default=datetime.utcnow)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    last_update = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Execution Feedback
    stdout = db.Column(db.Text)
    stderr = db.Column(db.Text)
    error_message = db.Column(db.Text)
    
    # Verification
    eth_tx_hash = db.Column(db.String(66), nullable=True)