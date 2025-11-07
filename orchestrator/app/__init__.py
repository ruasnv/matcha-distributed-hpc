#__init__.py
import os
import sqlite3
import click
from flask import Flask, request, jsonify, g, current_app # Import g for application context
from dotenv import load_dotenv

load_dotenv() # Ensure env vars are loaded

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES # This helps with parsing types like datetime
        )
        g.db.row_factory = sqlite3.Row # Return rows as dict-like objects
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    # Use app.root_path to correctly locate schema.sql, which is in the orchestrator/ directory
    # relative to the app's root (which is where __init__.py defines the app package)
    schema_path = os.path.join(current_app.root_path, '..', 'schema.sql')
    with open(schema_path, 'r') as f:
        db.executescript(f.read())

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        ORCHESTRATOR_API_KEY_PROVIDERS=os.environ.get('ORCHESTRATOR_API_KEY_PROVIDERS'),
        ORCHESTRATOR_API_KEY_CONSUMERS=os.environ.get('ORCHESTRATOR_API_KEY_CONSUMERS'),
        DATABASE=os.path.join(app.instance_path, 'federated_gpu.sqlite'),
        FLASK_ENV=os.environ.get('FLASK_ENV')
    )

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Basic API Key Authentication Middleware (for MVP)
    @app.before_request
    def check_api_key():
        # Exclude specific routes from API key check if needed (e.g., health checks)
        # Note: We'll add a separate route for testing purposes without auth temporarily
        if request.endpoint and request.endpoint.startswith('static') or \
            request.endpoint == 'api.health_check' or \
           (request.endpoint == 'api.get_all_providers_debug' and app.config['FLASK_ENV'] == 'development') or \
           (request.endpoint == 'api.get_all_tasks_debug' and app.config['FLASK_ENV'] == 'development'):
            return

        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({"error": "API Key missing"}), 401

        # Determine if the key is for a provider or a consumer based on path prefixes
        if request.path.startswith('/provider'):
            expected_key = app.config.get('ORCHESTRATOR_API_KEY_PROVIDERS')
        elif request.path.startswith('/consumer'):
            expected_key = app.config.get('ORCHESTRATOR_API_KEY_CONSUMERS')
        else:
            # Fallback if path doesn't match, or if you have public routes
            return jsonify({"error": "Unauthorized access route or API Key type unrecognized"}), 401

        if api_key != expected_key:
            return jsonify({"error": "Invalid API Key"}), 403
            
    # Register blueprints
    from . import routes
    app.register_blueprint(routes.bp)

    # Register database functions with the app
    app.teardown_appcontext(close_db) # Close DB connection when app context ends

    # Add a CLI command to initialize the database
    @app.cli.command('init-db')
    def init_db_command():
        """Clear the existing data and create new tables."""
        init_db()
        click.echo('Initialized the database.') # click is automatically available in Flask CLI
        
    return app