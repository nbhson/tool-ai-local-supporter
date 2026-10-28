import json
import uuid

from flask import Blueprint, Response, jsonify, request

import config
from services.helper_service import (
    get_lang_instruction,
    retrieve_chat_history,
    save_chat_message,
)
from services.logger import log
from services.models import ChatSession
from services.ollama_service import call_ollama
from services.repositories import ChatMessageRepository, ChatSessionRepository

chat_bp = Blueprint('chat', __name__)

# --- FREE CHAT ENDPOINTS ---

@chat_bp.route('/init', methods=['POST'])
def init_chat():
    data = request.json or {}
    model = data.get('model', config.DEFAULT_MODEL)
    ui_language = data.get('language', 'en')

    session_id = uuid.uuid4().hex
    log.route_request("POST", "/chat/init", model=model, language=ui_language)
    log.session_init(session_id, kind="chat")

    if ui_language == 'vi':
        greeting = "Xin chào! Tôi là trợ lý AI của bạn. Hôm nay tôi có thể giúp gì cho bạn?"
    else:
        greeting = "Hello! I am your AI assistant. How can I help you today?"

    # Create ChatSession in DB
    session = ChatSession(
        session_id=session_id,
        model=model,
        ui_language=ui_language
    )
    ChatSessionRepository.save(session)

    # Save initial greeting message
    save_chat_message(session_id, 'assistant', greeting)

    log.success("Chat session initialized", session_id=session_id[:12])
    return jsonify({
        "session_id": session_id,
        "greeting": greeting
    })

@chat_bp.route('/chat', methods=['POST'])
def chat_free():
    data = request.json
    if not data:
        return jsonify({"error": "No JSON data"}), 400
    session_id = data.get('session_id')
    question = data.get('question', '').strip()
    language = data.get('language', 'en')

    log.route_request("POST", "/chat/chat", session_id=(session_id or "")[:12], question_preview=question[:80])

    session = ChatSessionRepository.get_by_id(session_id)
    if not session:
        return jsonify({"error": "Session not found. Initialize chat first."}), 400
    if not question:
        return jsonify({"error": "Question cannot be empty"}), 400

    model = data.get('model', session.model or config.DEFAULT_MODEL)

    # Determine language instruction
    lang_instruction = get_lang_instruction(language)

    system_prompt = f"You are a helpful assistant. {lang_instruction}"

    messages = [{"role": "system", "content": system_prompt}]

    # Retrieve last messages from DB
    history = retrieve_chat_history(session_id, config.CHAT_HISTORY_LIMIT, skip_first=False)
    log.db_query("ChatMessage", session_id, count=len(history))
    messages.extend(history)

    # Save user message to history
    save_chat_message(session_id, 'user', question)

    # Append the new user question to active message context
    messages.append({"role": "user", "content": question})

    log.info("Free chat request ready", model=model, messages_count=len(messages))

    def generate():
        # Call Ollama using app context since we access DB inside generate()
        from app import app
        with app.app_context():
            import time
            ollama_start = time.time()
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

            ollama_ms = (time.time() - ollama_start) * 1000
            log.ollama_success(ollama_ms)

            # Save assistant response to DB
            save_chat_message(session_id, 'assistant', full_answer)
            log.info("Free chat response saved", answer_length=len(full_answer))

    return Response(generate(), mimetype='text/event-stream')

@chat_bp.route('/session/<session_id>/clear', methods=['POST'])
def clear_chat_session(session_id):
    log.route_request("POST", f"/chat/session/{session_id[:12]}/clear")

    session = ChatSessionRepository.get_by_id(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    # Reset conversation history but keep the first message (greeting)
    messages = ChatMessageRepository.get_messages_by_session_id(session_id)
    if messages:
        ChatMessageRepository.delete_messages(session_id, exclude_message_id=messages[0].id)
    log.success("Chat session cleared", session_id=session_id[:8])
    return jsonify({"success": True})

