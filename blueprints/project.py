import os
import uuid

from flask import Blueprint, Response, jsonify, request
from werkzeug.utils import secure_filename

import config
from services.agent_service import (
    generate_agent_stream,
    get_cached_project_tree,
    get_simple_tree_str,
    invalidate_project_tree_cache,
    scan_directory_and_stats,
    set_cached_project_tree,
)
from services.errors import InvalidRequestError, SessionNotFoundError
from services.helper_service import safe_join_project_path
from services.logger import log
from services.models import ProjectSession
from services.repositories import ProjectSessionRepository

project_bp = Blueprint('project', __name__)

EXCLUDE_DIRS = config.EXCLUDE_DIRS
EXCLUDE_FILES = config.EXCLUDE_FILES



@project_bp.route('/init', methods=['POST'])
def init_project():
    data = request.json or {}
    local_path = data.get('path', '').strip()
    model = data.get('model', config.DEFAULT_MODEL)
    ui_language = data.get('language', 'en')

    log.route_request("POST", "/project/init", path=local_path or "(upload)", model=model)

    session_id = uuid.uuid4().hex

    if not local_path:
        # Browser upload flow initialization
        log.info("Upload flow initialization")
        session = ProjectSession(
            session_id=session_id,
            is_local=False,
            status='init',
            model=model,
            ui_language=ui_language
        )
        ProjectSessionRepository.save(session)
        log.session_init(session_id, kind="project-upload")
        return jsonify({
            "session_id": session_id,
            "is_local": False
        })

    # Local path flow
    if not os.path.exists(local_path):
        error_msg = f"Thư mục không tồn tại: {local_path}" if ui_language == 'vi' else f"Directory does not exist: {local_path}"
        raise InvalidRequestError(error_msg)
    if not os.path.isdir(local_path):
        error_msg = f"Đường dẫn không phải là thư mục: {local_path}" if ui_language == 'vi' else f"Path is not a directory: {local_path}"
        raise InvalidRequestError(error_msg)
        
    try:
        tree, stats = scan_directory_and_stats(local_path, local_path)
        log.info("Project scanned", files=stats.get("total_files", 0), size=stats.get("total_size", 0))

        session = ProjectSession(
            session_id=session_id,
            project_path=local_path,
            is_local=True,
            status='ready',
            model=model,
            ui_language=ui_language
        )
        ProjectSessionRepository.save(session)
        log.session_init(session_id, kind="project-local")

        return jsonify({
            "session_id": session_id,
            "is_local": True,
            "tree": tree,
            "stats": stats
        })
    except Exception as e:
        log.error(f"Project init failed: {e}")
        return jsonify({"error": str(e)}), 500


@project_bp.route('/<session_id>/upload', methods=['POST'])
def upload_project_files(session_id):
    log.route_request("POST", f"/project/{session_id[:12]}/upload")

    session = ProjectSessionRepository.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError()

    files = request.files.getlist('files[]')
    paths = request.form.getlist('paths[]')

    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    log.info("Upload received", file_count=len(files))
    project_dir = os.path.join(config.UPLOAD_FOLDER, 'projects', session_id)
    os.makedirs(project_dir, exist_ok=True)

    try:
        # Phase 1 — validate all destination paths before saving anything,
        # so a single invalid path can't leave a half-written project dir.
        pending = []  # (file, dest_filepath)
        for idx, file in enumerate(files):
            # webkitRelativePath format is "root-folder-name/sub-folder/file.txt"
            path = (paths[idx] if idx < len(paths) else '').replace('\\', '/').strip()
            parts = path.split('/')
            if len(parts) > 1:
                # Strip the root folder name from relative path to keep structure cleaner
                rel_path = os.path.join(*parts[1:])
            elif path:
                rel_path = path
            else:
                # No path info — use the original filename (sanitized)
                rel_path = secure_filename(file.filename) if file.filename else ''
            if not rel_path:
                return jsonify({"error": "Missing path for an uploaded file"}), 400

            # Exclude folders by dir name (e.g. .git/, node_modules/)
            if any(part in EXCLUDE_DIRS for part in parts):
                continue

            # Guard against path traversal: safe_join_project_path resolves the
            # path and raises ValueError if it escapes project_dir.
            try:
                dest_filepath = safe_join_project_path(project_dir, rel_path)
            except ValueError:
                return jsonify({"error": f"Invalid file path: {path}"}), 400
            pending.append((file, dest_filepath))

        # Phase 2 — save validated files
        for file, dest_filepath in pending:
            os.makedirs(os.path.dirname(dest_filepath), exist_ok=True)
            file.save(dest_filepath)
        uploaded_count = len(pending)

        log.info("All files saved", uploaded_count=uploaded_count)
        session.project_path = project_dir
        session.status = 'ready'
        ProjectSessionRepository.save(session)

        tree, stats = scan_directory_and_stats(project_dir, project_dir)
        log.success("Project upload complete", files=stats.get("total_files", 0))

        return jsonify({
            "success": True,
            "tree": tree,
            "stats": stats
        })
    except Exception as e:
        session.status = 'failed'
        ProjectSessionRepository.save(session)
        log.error(f"Project upload failed: {e}")
        return jsonify({"error": str(e)}), 500

@project_bp.route('/<session_id>/file', methods=['GET'])
def get_project_file(session_id):
    session = ProjectSessionRepository.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError()
        
    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        raise InvalidRequestError("File path is required")
    if '..' in rel_path or rel_path.startswith('/'):
        raise InvalidRequestError("Invalid file path")
        
    filepath = os.path.join(session.project_path, rel_path)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
        
    if os.path.isdir(filepath):
        return jsonify({"error": "Path is a directory, not a file"}), 400
        
    try:
        # Read text content safely
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            
        return jsonify({
            "path": rel_path,
            "name": os.path.basename(rel_path),
            "content": content
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@project_bp.route('/<session_id>/write_file', methods=['POST'])
def write_project_file(session_id):
    session = ProjectSessionRepository.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError()
        
    data = request.json or {}
    rel_path = data.get('path', '').strip()
    content = data.get('content', '')
    
    if not rel_path:
        raise InvalidRequestError("File path is required")
    if '..' in rel_path or rel_path.startswith('/'):
        raise InvalidRequestError("Invalid file path")
        
    filepath = os.path.join(session.project_path, rel_path)
    try:
        # Create directories if writing a new file
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        invalidate_project_tree_cache(session_id)
        return jsonify({"success": True, "path": rel_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@project_bp.route('/<session_id>/scan', methods=['GET'])
def rescan_project(session_id):
    log.route_request("GET", f"/project/{session_id[:12]}/scan")

    session = ProjectSessionRepository.get_by_id(session_id)
    if not session:
        raise SessionNotFoundError()
    try:
        invalidate_project_tree_cache(session_id)
        tree, stats = scan_directory_and_stats(session.project_path, session.project_path)
        set_cached_project_tree(session_id, tree, stats)
        log.success("Project rescan complete", files=stats.get("total_files", 0))
        return jsonify({
            "tree": tree,
            "stats": stats
        })
    except Exception as e:
        log.error(f"Project scan failed: {e}")
        return jsonify({"error": str(e)}), 500



@project_bp.route('/<session_id>/chat', methods=['POST'])
def chat_project(session_id):
    log.route_request("POST", f"/project/{session_id[:12]}/chat")

    session = ProjectSessionRepository.get_by_id(session_id)
    if not session:
        log.warning("Session not found", session_id=session_id[:12])
        return jsonify({"error": "Session not found"}), 404

    project_path = session.project_path
    data = request.json or {}
    question = data.get('question', '').strip()
    language = data.get('language', 'en')
    model = data.get('model', session.model or config.DEFAULT_MODEL)
    context_files = data.get('context_files', [])
    agent_mode = data.get('agent_mode', True)

    log.session_chat_start(session_id, question, agent_mode)
    log.info("Request details", model=model, lang=language, context_files_count=len(context_files))

    if not question:
        return jsonify({"error": "Question is empty"}), 400

    # Read context files content
    context_str = ""
    if context_files:
        context_str_parts = [
            "\nADDITIONAL CONTEXT FILES SELECTED BY USER:",
            "CRITICAL: The content of these files is ALREADY provided below. Do NOT output or repeat the code of these files in your response."
        ]
        loaded_files = 0
        for rel_path in context_files:
            if not rel_path or '..' in rel_path or rel_path.startswith('/'):
                continue
            filepath = os.path.join(project_path, rel_path)
            if os.path.exists(filepath) and os.path.isfile(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    if len(content) > 15000:
                        content = content[:15000] + "\n\n...[content truncated to save context]..."
                    context_str_parts.append(f"\nFile: `{rel_path}`\n```\n{content}\n```")
                    loaded_files += 1
                except Exception as e:
                    context_str_parts.append(f"\nFile: `{rel_path}` (Error reading content: {e!s})")
        context_str = "\n".join(context_str_parts)
        log.info("Context files loaded", loaded_count=loaded_files, total_size=len(context_str))

    # Get initial project tree (limit depth for context)
    tree_nodes, stats = get_cached_project_tree(session_id)
    if tree_nodes is None:
        tree_nodes, stats = scan_directory_and_stats(project_path, project_path)
        set_cached_project_tree(session_id, tree_nodes, stats)
        log.debug("Project tree scanned (cache miss)")
    else:
        log.debug("Project tree from cache")
    tree_str = "\n".join(get_simple_tree_str(tree_nodes))

    # Delegate stream generation to services/agent_service.py
    def stream_response():
        return generate_agent_stream(
            session_id=session_id,
            project_path=project_path,
            question=question,
            language=language,
            model=model,
            context_str=context_str,
            tree_str=tree_str,
            agent_mode=agent_mode
        )

    response = Response(stream_response(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response
