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
    format="[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


_wal_listener_installed = False


def _enable_sqlite_wal(app):
    """Enable WAL mode + NORMAL synchronous on every new SQLite connection.

    Prevents "database is locked" errors under concurrent write loads. PRAGMA
    synchronous is per-connection, so it must be applied on every connect —
    not just the first one. The listener is registered once per process on the
    global Engine class and no-ops for non-SQLite connections, so it stays
    correct when the DB URI is overridden (e.g. tests using a temp database).
    """
    global _wal_listener_installed
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return
    if _wal_listener_installed:
        return
    _wal_listener_installed = True

    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        # Only touch real sqlite3 connections; skip other engines sharing the process
        if dbapi_connection.__class__.__module__ != "sqlite3":
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def create_app(config_overrides=None):
    """Application factory for the AI Local Supporter web app.

    Args:
        config_overrides: Optional dict applied on top of the defaults from
            config.py (e.g. tests overriding SQLALCHEMY_DATABASE_URI to point
            at a temporary database).
    """
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.config["SQLALCHEMY_DATABASE_URI"] = config.SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["CELERY_BROKER_URL"] = config.CELERY_BROKER_URL
    app.config["CELERY_RESULT_BACKEND"] = config.CELERY_RESULT_BACKEND
    if config_overrides:
        app.config.update(config_overrides)

    _enable_sqlite_wal(app)
    db.init_app(app)

    # Import models so SQLAlchemy metadata knows about them before create_all()
    import services.models  # noqa: F401

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    with app.app_context():
        db.create_all()

    # Import and register blueprints inside to prevent circular dependency
    from blueprints.chat import chat_bp
    from blueprints.doc import doc_bp
    from blueprints.project import project_bp

    app.register_blueprint(doc_bp, url_prefix="/api/doc")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")
    app.register_blueprint(project_bp, url_prefix="/api/project")

    from services.errors import AppError

    @app.errorhandler(AppError)
    def handle_app_error(error):
        return jsonify(error.to_dict()), error.status_code

    @app.route("/health")
    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Liveness/readiness report for the app's three backing services.

        Returns per-component status for database, Ollama and Celery. HTTP 200
        when every critical component is OK, 503 otherwise (Ollama/Celery are
        reported but do not fail the request — the app degrades gracefully
        without them).
        """
        checks = {}

        # Database — must be reachable for the app to function at all
        try:
            from sqlalchemy import text

            db.session.execute(text("SELECT 1"))
            db.session.rollback()
            checks["database"] = {"status": "ok"}
        except Exception as e:
            checks["database"] = {"status": "error", "detail": str(e)}

        # Ollama — inference backend; app starts without it but chat won't work
        try:
            response = requests.get(f"{config.OLLAMA_URL}/tags", timeout=2)
            response.raise_for_status()
            checks["ollama"] = {"status": "ok"}
        except Exception:
            checks["ollama"] = {"status": "unavailable"}

        # Celery — background document processing; app degrades without workers
        try:
            from celery_app import celery

            ping = celery.control.ping(timeout=1.0)
            checks["celery"] = {"status": "ok" if ping else "unreachable"}
        except Exception:
            checks["celery"] = {"status": "unreachable"}

        healthy = checks["database"]["status"] == "ok"
        return jsonify(
            {
                "status": "healthy" if healthy else "unhealthy",
                "checks": checks,
            }
        ), (200 if healthy else 503)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/models", methods=["GET"])
    def list_models():
        global _cached_models, _cached_time
        now = time.time()
        # Cache Ollama models tags list for 60 seconds
        if _cached_models is None or now - _cached_time > 60:
            try:
                response = requests.get(f"{config.OLLAMA_URL}/tags", timeout=10)
                response.raise_for_status()
                models_data = response.json()
                _cached_models = [m["name"] for m in models_data.get("models", [])]
                _cached_time = now
            except Exception:
                return jsonify({"models": [config.DEFAULT_MODEL]})
        return jsonify({"models": _cached_models})

    return app
