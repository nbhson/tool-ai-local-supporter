import os
import sys

# Ensure the current project directory is in the python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from celery import Celery

import config

celery = Celery(
    "ai_local_support",
    broker=config.CELERY_BROKER_URL,
    backend=config.CELERY_RESULT_BACKEND
)

celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_pool='solo',
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

# Application Context integration
_flask_app = None

def get_flask_app():
    global _flask_app
    if _flask_app is None:
        from app_factory import create_app
        _flask_app = create_app()
    return _flask_app

class FlaskContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
        app = get_flask_app()
        with app.app_context():
            return self.run(*args, **kwargs)

celery.Task = FlaskContextTask
