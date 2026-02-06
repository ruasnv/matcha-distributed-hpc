import os
import click
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from .models import db, Provider, Task # Import db and models
from flask_cors import CORS

load_dotenv() 
def create_app():
    app = Flask(__name__, instance_relative_config=True)
    CORS(app)

    # 1. Determine and Clean the database URL
    db_url = os.environ.get('DATABASE_URL')
    
    if db_url:
        # FIX: Neon/Render often provide 'postgres://', but SQLAlchemy 1.4+ 
        # requires 'postgresql://' to function correctly.
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        print("🌐 Using Cloud Postgres (Neon/Render)")
    else:
        # Fallback to local SQLite for local testing if no cloud DB is linked
        db_url = "sqlite:///matcha.db"
        print("⚠️ No DATABASE_URL found. Using local SQLite: matcha.db")

    # 2. Load configurations
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-key-123'),
        ORCHESTRATOR_API_KEY_PROVIDERS='debug-provider-key',
        ORCHESTRATOR_API_KEY_CONSUMERS=os.environ.get('ORCHESTRATOR_API_KEY_CONSUMERS', 'debug-consumer-key'),
        SQLALCHEMY_DATABASE_URI=db_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # NEW: Neon requires SSL. This tells SQLAlchemy to use it.
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"sslmode": "require"} if db_url.startswith("postgresql") else {}
        },
        FLASK_ENV=os.environ.get('FLASK_ENV', 'development')
    )
    
    # 3. Initialize extensions AFTER config is set
    db.init_app(app)

    with app.app_context():
        # This creates your local 'matcha.db' file automatically
        db.create_all()
        print("✅ Database tables initialized.")

    # ... keep the rest of your middleware and blueprint registration ...

    
    # Basic API Key Authentication Middleware (for MVP)
    @app.before_request
    def check_api_key():
        if request.method == 'OPTIONS':
            return

        # Add the consumer task routes to the exclusion list
        excluded_endpoints = [
            'static', 
            'health_check', 
            'sync_user', 
            'upload_project',
            'consumer_submit_task',
            'get_user_tasks', # The name of your task-fetching function
            'get_all_tasks_debug' # The debug route you added
        ]

        if request.endpoint and any(ex in request.endpoint for ex in excluded_endpoints):
            return

        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({"error": "API Key missing"}), 401

        if request.path.startswith('/provider') or request.path.startswith('/agent'):
            expected_key = app.config.get('ORCHESTRATOR_API_KEY_PROVIDERS')
        elif request.path.startswith('/consumer'):
            expected_key = app.config.get('ORCHESTRATOR_API_KEY_CONSUMERS')
        else:
            return jsonify({"error": "Unauthorized path"}), 401

        if api_key != expected_key:
            print(f"AUTH FAILED: {api_key} != {expected_key}") # Print the failure
            return jsonify({"error": "Invalid API Key"}), 403

    # Register blueprints
    from . import routes
    app.register_blueprint(routes.bp)

    return app