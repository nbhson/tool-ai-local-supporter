from datetime import datetime

from sqlalchemy.orm import deferred

from services.database import db


class DocumentSession(db.Model):
    __tablename__ = 'document_sessions'
    
    session_id = db.Column(db.String(36), primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(512), nullable=False)
    status = db.Column(db.String(50), default='processing')  # 'processing', 'ready', 'failed'
    error_message = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(10), default='en')
    model = db.Column(db.String(100), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)      # 'document', 'image'
    base64_image = deferred(db.Column(db.Text, nullable=True))          # Stored for vision model
    extracted_text = deferred(db.Column(db.Text, nullable=True))        # Backup/preview text
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    files = db.relationship('DocumentFile', backref='session', lazy=True, cascade="all, delete-orphan")

class DocumentFile(db.Model):
    __tablename__ = 'document_files'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), db.ForeignKey('document_sessions.session_id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(512), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)      # 'document', 'image'
    base64_image = deferred(db.Column(db.Text, nullable=True))          # Stored for vision model
    extracted_text = deferred(db.Column(db.Text, nullable=True))        # Backup/preview text
    status = db.Column(db.String(50), default='processing')    # 'processing', 'ready', 'failed'
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'
    
    session_id = db.Column(db.String(36), primary_key=True)
    model = db.Column(db.String(100), nullable=False)
    ui_language = db.Column(db.String(10), default='en')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProjectSession(db.Model):
    __tablename__ = 'project_sessions'
    
    session_id = db.Column(db.String(36), primary_key=True)
    project_path = db.Column(db.String(512), nullable=True)  # Absolute local path (if any)
    is_local = db.Column(db.Boolean, default=False)          # True if workspace opened directly from local drive
    status = db.Column(db.String(50), default='processing')  # 'processing', 'ready', 'failed'
    model = db.Column(db.String(100), nullable=False)
    ui_language = db.Column(db.String(10), default='en')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), index=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)           # 'system', 'user', 'assistant'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
