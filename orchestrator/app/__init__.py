import os
import click
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from .models import db, Provider, Task # Import db and models
from flask_cors import CORS

load_dotenv() 

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    CORS(app)  # Enable CORS for all routes
    # Load config from environment variables
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        ORCHESTRATOR_API_KEY_PROVIDERS=os.environ.get('ORCHESTRATOR_API_KEY_PROVIDERS'),
        ORCHESTRATOR_API_KEY_CONSUMERS=os.environ.get('ORCHESTRATOR_API_KEY_CONSUMERS'),
        # This is the magic line that reads the DATABASE_URL from Render
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        FLASK_ENV=os.environ.get('FLASK_ENV')
    )

    # Initialize extensions
    db.init_app(app)

    with app.app_context():
        # This is the "no-shell" magic:
        # It creates all tables if they don't exist
        db.create_all()

    # Basic API Key Authentication Middleware (for MVP)
    @app.before_request
    def check_api_key():
        # Exclude specific routes from API key check
        if request.endpoint and (
            request.endpoint.startswith('static') or
            request.endpoint == 'api.health_check' or
            (request.endpoint == 'api.get_all_providers_debug' and app.config['FLASK_ENV'] == 'development') or
            (request.endpoint == 'api.get_all_tasks_debug' and app.config['FLASK_ENV'] == 'development')
        ):
            return

        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({"error": "API Key missing"}), 401

        # Determine if the key is for a provider or a consumer based on path prefixes
        if request.path.startswith('/provider') or request.path.startswith('/agent'):
            expected_key = app.config.get('ORCHESTRATOR_API_KEY_PROVIDERS')
        elif request.path.startswith('/consumer'):
            expected_key = app.config.get('ORCHESTRATOR_API_KEY_CONSUMERS')
        else:
            return jsonify({"error": "Unauthorized access route or API Key type unrecognized"}), 401

        if api_key != expected_key:
            return jsonify({"error": "Invalid API Key"}), 403

    # Register blueprints
    from . import routes
    app.register_blueprint(routes.bp)

    return app