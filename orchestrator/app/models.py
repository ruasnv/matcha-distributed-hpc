from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize the database extension
db = SQLAlchemy()

class Provider(db.Model):
    __tablename__ = 'providers'
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String, nullable=False)
    gpus = db.Column(db.Text, nullable=False)  # Stored as JSON string
    address = db.Column(db.String, nullable=False)
    last_seen = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String, nullable=False, default='active')

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.String, primary_key=True)
    consumer_id = db.Column(db.String, nullable=False)
    docker_image = db.Column(db.String, nullable=False)
    gpu_requirements = db.Column(db.Text)  # Stored as JSON string
    provider_id = db.Column(db.String, db.ForeignKey('providers.id'), nullable=True)
    gpu_assigned = db.Column(db.Text)  # Stored as JSON string
    status = db.Column(db.String, nullable=False)
    submission_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_update = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    stdout = db.Column(db.Text, nullable=True)
    stderr = db.Column(db.Text, nullable=True)
    input_path = db.Column(db.String, nullable=True)
    output_path = db.Column(db.String, nullable=True)
    script_path = db.Column(db.String, nullable=True)
    # We'll store secrets (like AWS/R2 keys) in an encrypted JSON string
    env_vars = db.Column(db.Text, nullable=True)
    