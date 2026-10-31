import os

UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max
ALLOWED_EXTENSIONS = {
    'txt', 'pdf', 'docx', 'doc', 'md', 'csv', 'json', 'xml', 'yaml', 'yml',
    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'tif', 'webp'
}

# Ollama configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "qwen2.5-coder:14b")
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'tif', 'webp'}
VISION_MODELS = {'qwen2.5-vl', 'qwen2.5vl', 'llava', 'bakllava', 'moondream', 'cog-vlm'}

# Database & Celery Configuration
SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///ai_local_support.db")
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# Embedding Configuration for RAG
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")
FASTEMBED_MODEL = os.environ.get("FASTEMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5-Q")

# Refactoring Readability & Magic Numbers Config
AGENT_MAX_ITERATIONS = 10
AGENT_MAX_DEPTH = 2
AGENT_MAX_ENTRIES_PER_DIR = 30
AGENT_TREE_CACHE_TTL = 300  # 5 minutes

# RAG Configuration
RAG_TOP_K = 6               # Increased from 4 for better hybrid retrieval
RAG_CHUNK_SIZE = 1000
RAG_CHUNK_OVERLAP = 200
RAG_HYBRID_VECTOR_WEIGHT = 0.6  # Weight for vector similarity in hybrid search
RAG_HYBRID_KEYWORD_WEIGHT = 0.4  # Weight for keyword matching in hybrid search

# Tool Configuration
TOOL_READ_TIMEOUT = 30      # seconds
TOOL_WRITE_TIMEOUT = 30     # seconds
TOOL_COMMAND_TIMEOUT = 30   # seconds for RUN_COMMAND
TOOL_TEST_TIMEOUT = 60      # seconds for RUN_TESTS
TOOL_LINT_TIMEOUT = 60      # seconds for LINT_CODE
TOOL_GIT_TIMEOUT = 15       # seconds for GIT commands

# Image Processing
IMAGE_COMPRESS_MAX_SIZE = (1024, 1024)
IMAGE_COMPRESS_QUALITY = 85

# Session & Cleanup
CLEANUP_EXPIRE_SECONDS = 24 * 3600  # 1 day

# Chat History
CHAT_HISTORY_LIMIT = 10
PROJECT_HISTORY_LIMIT = 8
CHAT_HISTORY_SUMMARY_THRESHOLD = 6  # Summarize when history exceeds this
MAX_TEXT_CHARS = 15000

EXCLUDE_DIRS = {
    '.git', 'node_modules', '.venv', 'venv', 'env', '.idea', '__pycache__',
    'dist', 'build', 'target', '.npm', '.cache', '.angular', '.next', '.nuxt',
    '.sass-cache', '.svelte-kit', '.agents', '.gemini', 'coverage', '.nyc_output',
    '.pytest_cache', '.vscode', '.tox'
}
EXCLUDE_FILES = {'.DS_Store', 'Thumbs.db'}


