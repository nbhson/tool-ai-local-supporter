import json
import os
import threading
import time
import uuid

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    send_from_directory,
)
from werkzeug.utils import secure_filename

import config
from services.document_service import allowed_file, cleanup_old_uploads, is_image_file
from services.helper_service import (
    get_lang_instruction,
    retrieve_chat_history,
    save_chat_message,
)
from services.models import DocumentFile, DocumentSession
from services.ollama_service import call_ollama, is_vision_model
from services.rag_service import retrieve_context
from services.repositories import ChatMessageRepository, DocumentSessionRepository
from tasks import process_document_task

doc_bp = Blueprint('doc', __name__)

# Throttle cleanup_old_uploads to run at most once per 5 minutes
_last_cleanup_time = 0
_cleanup_lock = threading.Lock()

@doc_bp.route('/upload', methods=['POST'])
def upload_document():
    # Run cleanup in background (throttled to max once every 5 minutes)
    global _last_cleanup_time
    upload_dir = current_app.config['UPLOAD_FOLDER']
    with _cleanup_lock:
        now = time.time()
        if now - _last_cleanup_time > 300:
            _last_cleanup_time = now
            threading.Thread(target=cleanup_old_uploads, args=(upload_dir,), daemon=True).start()
    
    # Support both list of files and single file
    uploaded_files = []
    if 'files' in request.files:
        uploaded_files = request.files.getlist('files')
    elif 'file' in request.files:
        uploaded_files = request.files.getlist('file')
        
    uploaded_files = [f for f in uploaded_files if f.filename != '']
    
    if not uploaded_files:
        return jsonify({"error": "No file provided"}), 400
        
    if len(uploaded_files) > 3:
        return jsonify({"error": "Tối đa 3 files được phép tải lên"}), 400

    model = request.form.get('model', config.DEFAULT_MODEL)
    language = request.form.get('language', 'en')  # Default to English
    
    # Validate allowed extensions for all files first
    for file in uploaded_files:
        if not allowed_file(file.filename):
            return jsonify({"error": f"File type not supported for: {file.filename}"}), 400

    session_id = uuid.uuid4().hex
    saved_files = []

    for file in uploaded_files:
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(upload_dir, unique_filename)
        file.save(filepath)

        is_image = is_image_file(filepath)
        file_type = "image" if is_image else "document"
        
        saved_files.append({
            "filename": filename,
            "filepath": filepath,
            "file_type": file_type
        })

    # Join filenames for the primary session metadata
    all_filenames = ", ".join([f["filename"] for f in saved_files])
    if len(all_filenames) > 255:
        all_filenames = all_filenames[:252] + "..."

    # Create DocumentSession in database with status='processing'
    # Use first file's details as fallback for session fields
    first_file = saved_files[0]
    session = DocumentSession(
        session_id=session_id,
        filename=all_filenames,
        filepath=first_file["filepath"],
        status='processing',
        language=language,
        model=model,
        file_type="image" if any(f["file_type"] == "image" for f in saved_files) else "document"
    )

    # Create individual DocumentFile records
    doc_files = []
    for f in saved_files:
        doc_files.append(DocumentFile(
            session_id=session_id,
            filename=f["filename"],
            filepath=f["filepath"],
            file_type=f["file_type"],
            status='processing'
        ))

    # Single commit for session + all files (reduces N+1 DB commits)
    DocumentSessionRepository.save_all(session, *doc_files)

    # Trigger Celery background task with only session_id
    process_document_task.delay(session_id, language, model)

    return jsonify({
        "session_id": session_id,
        "status": "processing",
        "filename": all_filenames
    })

@doc_bp.route('/status/<session_id>', methods=['GET'])
def get_session_status(session_id):
    session = DocumentSessionRepository.get_by_id(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    files = DocumentSessionRepository.get_files_by_session_id(session_id)
    files_data = [{
        "filename": f.filename,
        "file_type": f.file_type,
        "status": f.status,
        "error": f.error_message,
        "unique_filename": os.path.basename(f.filepath) if f.filepath else None
    } for f in files]

    if session.status == 'ready':
        # Get greeting message from DB (optimized: fetch only the first assistant message)
        greeting = ""
        first_assistant = ChatMessageRepository.get_first_assistant_message(session_id)
        if first_assistant:
            greeting = first_assistant.content
        return jsonify({
            "status": "ready",
            "session_id": session_id,
            "filename": session.filename,
            "file_type": session.file_type,
            "greeting": greeting,
            "text_preview": (session.extracted_text or "")[:500],
            "files": files_data
        })
    elif session.status == 'failed':
        return jsonify({
            "status": "failed",
            "error": session.error_message or "An error occurred during file processing.",
            "files": files_data
        })
    else:
        return jsonify({
            "status": "processing",
            "files": files_data
        })

@doc_bp.route('/chat', methods=['POST'])
def chat_document():
    data = request.json
    if not data:
        return jsonify({"error": "No JSON data"}), 400
    session_id = data.get('session_id')
    question = data.get('question', '').strip()
    language = data.get('language', 'en')
    
    session = DocumentSessionRepository.get_by_id(session_id)
    if not session:
        return jsonify({"error": "Session not found. Upload a file first."}), 400
    if not question:
        return jsonify({"error": "Question cannot be empty"}), 400

    model = data.get('model', session.model or config.DEFAULT_MODEL)

    # Determine language instruction
    lang_instruction = get_lang_instruction(language)

    # Retrieve all ready base64 images from DocumentFile table
    files = DocumentSessionRepository.get_files_by_session_id(session_id)
    image_files = [f for f in files if f.file_type == 'image' and f.status == 'ready']
    base64_images = [img.base64_image for img in image_files if img.base64_image]

    use_vision = is_vision_model(model) and len(base64_images) > 0

    if use_vision:
        # Perform RAG retrieval for context alongside image details
        context = retrieve_context(session_id, question, top_k=config.RAG_TOP_K)
        
        system_prompt = f"""You are a document analysis assistant. Answer the user question based on the provided context and images.
If the answer cannot be found in the context or images, say "I cannot find the answer in the document."

Context from document:
{context}

{lang_instruction}"""
        messages = [{"role": "system", "content": system_prompt}]
        
        messages.extend(retrieve_chat_history(session_id, config.CHAT_HISTORY_LIMIT, skip_first=True))
            
        messages.append({
            "role": "user",
            "content": question,
            "images": base64_images
        })
    else:
        # Perform RAG retrieval for documents or image-with-OCR fallback
        context = retrieve_context(session_id, question, top_k=config.RAG_TOP_K)
        
        system_prompt = f"""You are a document analysis assistant. Answer the user question based ONLY on the provided context.
If the answer cannot be found in the context, say "I cannot find the answer in the document."

Context from document:
{context}

{lang_instruction}"""
        messages = [{"role": "system", "content": system_prompt}]
        
        messages.extend(retrieve_chat_history(session_id, config.CHAT_HISTORY_LIMIT, skip_first=True))
            
        messages.append({"role": "user", "content": question})

    # Save user message to database
    save_chat_message(session_id, 'user', question)

    def generate():
        from app import app
        with app.app_context():
            generator = call_ollama(messages, model, stream=True)
            full_answer = ""
            for chunk in generator:
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str != "[DONE]":
                        try:
                            data_json = json.loads(data_str)
                            if "content" in data_json:
                                full_answer += data_json["content"]
                        except:
                            pass
                yield chunk
            
            # Save assistant response to DB
            save_chat_message(session_id, 'assistant', full_answer)

    return Response(generate(), mimetype='text/event-stream')

@doc_bp.route('/session/<session_id>/clear', methods=['POST'])
def clear_doc_session(session_id):
    session = DocumentSessionRepository.get_by_id(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
        
    # Reset conversation history but keep the first message (greeting)
    messages = ChatMessageRepository.get_messages_by_session_id(session_id)
    if messages:
        ChatMessageRepository.delete_messages(session_id, exclude_message_id=messages[0].id)
    return jsonify({"success": True})

@doc_bp.route('/files/<filename>', methods=['GET'])
def get_uploaded_file(filename):
    upload_dir = current_app.config['UPLOAD_FOLDER']
    return send_from_directory(upload_dir, filename)
