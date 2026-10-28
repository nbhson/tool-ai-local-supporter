import json
import os

from services.logger import log
from services.models import ChatMessage
from services.repositories import ChatMessageRepository


def get_lang_instruction(language):
    return "Respond in English." if language == "en" else "Respond in Vietnamese."

def format_sse_event(event_type, **kwargs):
    payload = json.dumps({'type': event_type, **kwargs})
    # Reduced padding from 1024 to 512 bytes — still sufficient to force
    # proxy/buffer flushes while halving per-event network overhead.
    padding = ":" + " " * 512 + "\n"
    return f"data: {payload}\n\n{padding}"

def _summarize_old_messages(messages):
    """Summarize older messages into a compact representation to save context window.
    
    Keeps the last 3 messages in full, and summarizes everything before that
    into a brief summary.
    """
    if len(messages) <= 4:
        return messages
    
    older = messages[:-3]
    recent = messages[-3:]
    
    # Build a compact summary of older messages
    summary_parts = []
    for msg in older:
        role = "User" if msg['role'] == 'user' else "Assistant"
        content = msg['content']
        # Truncate each old message to first 150 chars
        if len(content) > 150:
            content = content[:150] + "..."
        summary_parts.append(f"{role}: {content}")
    
    summary_text = "[Earlier conversation summary]\n" + "\n".join(summary_parts)
    
    # Prepend summary as a system-context message
    summarized = [{"role": "user", "content": f"[System: The following is a summary of earlier messages in this conversation]\n{summary_text}"},
                  {"role": "assistant", "content": "Understood, I have the context of our earlier conversation."}]
    summarized.extend(recent)
    return summarized


def retrieve_chat_history(session_id, limit, skip_first=False):
    """Retrieve the last N chat messages for a session.
    
    When history exceeds 6 messages, older messages are summarized
    to save context window space while preserving important context.
    """
    if skip_first:
        first_msg = ChatMessage.query.filter_by(session_id=session_id).order_by(ChatMessage.created_at.asc()).first()
        if not first_msg:
            log.db_query("ChatMessage", session_id, count=0)
            return []
        first_id = first_msg.id
        
        # Fetch limit + 1 messages to ensure we get up to `limit` messages after skipping the first one
        recent = ChatMessageRepository.get_messages_by_session_id(session_id, limit=limit + 1)
        recent = [msg for msg in recent if msg.id != first_id][-limit:]
    else:
        recent = ChatMessageRepository.get_messages_by_session_id(session_id, limit=limit)
    
    messages = [{"role": msg.role, "content": msg.content} for msg in recent]
    
    # Apply summarization for longer histories to save context window
    if len(messages) > 6:
        before_count = len(messages)
        messages = _summarize_old_messages(messages)
        log.info(f"History summarized: {before_count} → {len(messages)} messages", session=session_id[:8])
    
    return messages

def save_chat_message(session_id, role, content):
    """Helper to save a message in the database."""
    preview = content[:80].replace("\n", " ") if content else ""
    msg = ChatMessage(session_id=session_id, role=role, content=content)
    result = ChatMessageRepository.save(msg)
    log.db_save("ChatMessage", session_id, extra=f"role={role} │ preview={preview}")
    return result

def safe_join_project_path(base_path: str, relative_path: str) -> str:
    """Joins base_path and relative_path and verifies that the resulting path is inside base_path."""
    if not relative_path:
        raise ValueError("Relative path is empty")
    base_abs = os.path.abspath(base_path)
    joined_path = os.path.join(base_abs, relative_path)
    target_abs = os.path.abspath(joined_path)
    
    prefix = base_abs if base_abs.endswith(os.path.sep) else base_abs + os.path.sep
    if not target_abs.startswith(prefix) and target_abs != base_abs:
        raise ValueError("Invalid path: Path traversal detected")
        
    return target_abs


