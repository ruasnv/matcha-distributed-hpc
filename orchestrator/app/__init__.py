import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask_cors import CORS
from .models import db

load_dotenv() 

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    CORS(app, origins=["https://matcha-kolektif-ui.onrender.com", "http://localhost:5173"])

    # 1. Database URL Cleaning
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        print("🌐 Using Cloud Postgres (Neon/Render)")
    else:
        db_url = "sqlite:///matcha.db"
        print("⚠️ No DATABASE_URL found. Using local SQLite.")

    # 2. Config Mapping
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-key-123'),
        ORCHESTRATOR_API_KEY_PROVIDERS='debug-provider-key',
        ORCHESTRATOR_API_KEY_CONSUMERS=os.environ.get('ORCHESTRATOR_API_KEY_CONSUMERS', 'debug-consumer-key'),
        SQLALCHEMY_DATABASE_URI=db_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"sslmode": "require"} if db_url.startswith("postgresql") else {}
        }
    )

    db.init_app(app)

    with app.app_context():
        try:
            # This is the "safe" way to do it in production
            db.create_all()
            print("✅ Database tables verified/initialized.")
        except Exception as e:
            # If a worker fails because another worker already created the table,
            # we just log it and move on instead of crashing.
            print(f"⚠️ Database initialization note: {e}")    

    # --- THE FIXES ARE BELOW ---

    @app.before_request
    def check_api_key():
        if request.method == 'OPTIONS':
            return

        # 1. THE TRUTH SOURCE: Check the actual URL path
        # If the user is at the root, or loading the favicon, let them through!
        if request.path == "/" or "favicon.ico" in request.path:
            return

        # 2. List of paths that DON'T need a key
        # Note: These are substrings of your URLs
        public_paths = [
            '/health_check', 
            '/sync_user', 
            '/upload_project', 
            '/consumer/tasks'
        ]

        if any(path in request.path for path in public_paths):
            return

        # 3. AUTH LOGIC
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            # We add the path to the error so we can debug exactly what is being blocked
            return jsonify({"error": f"API Key missing for {request.path}"}), 401
        
        # Determine which key to check
        if request.path.startswith('/provider') or request.path.startswith('/agent'):
            expected_key = app.config.get('ORCHESTRATOR_API_KEY_PROVIDERS')
        elif request.path.startswith('/consumer'):
            expected_key = app.config.get('ORCHESTRATOR_API_KEY_CONSUMERS')
        else:
            return jsonify({"error": "Unauthorized path structure"}), 401

        if api_key != expected_key:
            return jsonify({"error": "Invalid API Key"}), 403
        
    # Add a root route so you don't get a 404 when testing the URL
    @app.route('/')
    def index():
        return jsonify({"status": "Matcha Orchestrator Live", "database": "Connected"}), 200

    from . import routes
    app.register_blueprint(routes.bp)

    return app