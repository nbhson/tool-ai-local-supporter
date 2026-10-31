from services.database import db
from services.models import (
    ChatMessage,
    ChatSession,
    DocumentFile,
    DocumentSession,
    ProjectSession,
)


class DocumentSessionRepository:
    @staticmethod
    def get_by_id(session_id):
        return db.session.get(DocumentSession, session_id)

    @staticmethod
    def save(session):
        db.session.add(session)
        db.session.commit()
        return session

    @staticmethod
    def save_all(*instances):
        """Add multiple instances to the session and commit once (reduces N+1 commits)."""
        for inst in instances:
            db.session.add(inst)
        db.session.commit()
        return instances

    @staticmethod
    def get_files_by_session_id(session_id):
        return DocumentFile.query.filter_by(session_id=session_id).all()


class ChatSessionRepository:
    @staticmethod
    def get_by_id(session_id):
        return db.session.get(ChatSession, session_id)

    @staticmethod
    def save(session):
        db.session.add(session)
        db.session.commit()
        return session

class ProjectSessionRepository:
    @staticmethod
    def get_by_id(session_id):
        return db.session.get(ProjectSession, session_id)

    @staticmethod
    def save(session):
        db.session.add(session)
        db.session.commit()
        return session

class ChatMessageRepository:
    @staticmethod
    def get_messages_by_session_id(session_id, limit=None):
        if limit:
            messages = ChatMessage.query.filter_by(session_id=session_id)\
                .order_by(ChatMessage.created_at.desc())\
                .limit(limit)\
                .all()
            messages.reverse()
            return messages
        return ChatMessage.query.filter_by(session_id=session_id).order_by(ChatMessage.created_at.asc()).all()

    @staticmethod
    def get_first_assistant_message(session_id):
        """Fetch only the first assistant message for a session (avoids loading all messages)."""
        return ChatMessage.query.filter_by(session_id=session_id, role='assistant')\
            .order_by(ChatMessage.created_at.asc()).first()

    @staticmethod
    def save(message):
        db.session.add(message)
        db.session.commit()
        return message

    @staticmethod
    def delete_messages(session_id, exclude_message_id=None):
        query = ChatMessage.query.filter(ChatMessage.session_id == session_id)
        if exclude_message_id is not None:
            query = query.filter(ChatMessage.id != exclude_message_id)
        query.delete()
        db.session.commit()
