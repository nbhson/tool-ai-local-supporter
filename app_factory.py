import logging
import os
import time

import requests
from flask import Flask, jsonify, render_template

import config
from services.database import db

_cached_models = None
_cached_time = 0


logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
    app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['CELERY_BROKER_URL'] = config.CELERY_BROKER_URL
    app.config['CELERY_RESULT_BACKEND'] = config.CELERY_RESULT_BACKEND

    db.init_app(app)
    
    # Import models so SQLAlchemy metadata knows about them before create_all()
    import services.models  # noqa: F401
    
    # Enable WAL mode for SQLite to prevent "database is locked" errors under concurrent write loads.
    # Using a flag to ensure PRAGMA is set only once per process, not on every connection.
    _sqlite_pragma_set = False
    if config.SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
        @event.listens_for(Engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            nonlocal _sqlite_pragma_set
            if not _sqlite_pragma_set:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()
                _sqlite_pragma_set = True
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    with app.app_context():
        db.create_all()
        
    # Import and register blueprints inside to prevent circular dependency
    from blueprints.chat import chat_bp
    from blueprints.doc import doc_bp
    from blueprints.project import project_bp
    
    app.register_blueprint(doc_bp, url_prefix='/api/doc')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    app.register_blueprint(project_bp, url_prefix='/api/project')
    
    from services.errors import AppError
    @app.errorhandler(AppError)
    def handle_app_error(error):
        return jsonify(error.to_dict()), error.status_code

    @app.route('/')
    def index():
        return render_template('index.html')



    @app.route('/api/models', methods=['GET'])
    def list_models():
        global _cached_models, _cached_time
        now = time.time()
        # Cache Ollama models tags list for 60 seconds
        if _cached_models is None or now - _cached_time > 60:
            try:
                response = requests.get(f"{config.OLLAMA_URL}/tags", timeout=10)
                response.raise_for_status()
                models_data = response.json()
                _cached_models = [m['name'] for m in models_data.get('models', [])]
                _cached_time = now
            except Exception:
                return jsonify({"models": [config.DEFAULT_MODEL]})
        return jsonify({"models": _cached_models})
            
    return app
