import base64
import logging

from celery_app import celery
from services.database import db
from services.document_service import (
    extract_text_from_file,
    extract_text_from_image_ocr,
    is_image_file,
    resize_and_compress_image,
)
from services.models import ChatMessage, DocumentFile, DocumentSession
from services.ollama_service import is_vision_model
from services.rag_service import index_document


def _process_single_file(doc_file, model, is_vision):
    """Processes a single document or image file and returns (extracted_text, base64_image, error)."""
    is_image = is_image_file(doc_file.filepath)
    extracted_text = ""
    base64_image = None
    
    if is_image:
        base64_image = resize_and_compress_image(doc_file.filepath)
        if not base64_image:
            with open(doc_file.filepath, 'rb') as img_file:
                base64_image = base64.b64encode(img_file.read()).decode('utf-8')
        
        # Check if model supports vision
        if not is_vision:
            logging.info(f"Model {model} is not a vision model. Falling back to OCR for {doc_file.filename}.")
            ocr_text = extract_text_from_image_ocr(doc_file.filepath)
            if ocr_text:
                if ocr_text.startswith("OCR Error"):
                    raise Exception(ocr_text)
                extracted_text = ocr_text
            else:
                extracted_text = f"[Không tìm thấy văn bản nào trong hình ảnh / No text detected in this image: {doc_file.filename}]"
        else:
            extracted_text = "[Image analyzed via vision model]"
    else:
        extracted_text = extract_text_from_file(doc_file.filepath)
        if extracted_text is None or extracted_text.startswith("Error"):
            raise Exception(extracted_text or "Text extraction failed.")
            
    return extracted_text, base64_image

def _build_greeting(doc_files, vision_images_count, language):
    """Formulate the greeting message based on processed files."""
    filenames_list = [f.filename for f in doc_files]
    filenames_str = ", ".join(filenames_list)
    if len(filenames_str) > 60:
        filenames_str = filenames_str[:57] + "..."
        
    if vision_images_count > 0:
        return (
            f"Tôi đã nhận diện {vision_images_count} hình ảnh ({filenames_str}). Bạn cần tôi trợ giúp gì về các hình ảnh này?"
            if language == 'vi' else
            f"I have processed {vision_images_count} images ({filenames_str}). How can I help you with them?"
        )
    else:
        return (
            f"Tôi đã phân tích xong {len(doc_files)} tài liệu ({filenames_str}). Bạn cần tôi giúp gì về nội dung này?"
            if language == 'vi' else
            f"I have analyzed {len(doc_files)} documents ({filenames_str}). How can I help you with them?"
        )

@celery.task(name="tasks.process_document_task", bind=True, max_retries=3)
def process_document_task(self, session_id, language, model):
    """Asynchronously process multiple documents/images: extract text/image, run OCR, chunk and embed into ChromaDB."""
    try:
        logging.info(f"Starting background processing for session {session_id}")
        session = DocumentSession.query.get(session_id)
        if not session:
            logging.error(f"Session {session_id} not found in database.")
            return
            
        doc_files = DocumentFile.query.filter_by(session_id=session_id).all()
        if not doc_files:
            logging.error(f"No files found for session {session_id} in DocumentFile.")
            return
        
        all_text_chunks = []
        vision_images = []
        is_vision = is_vision_model(model)
        
        for doc_file in doc_files:
            try:
                logging.info(f"Processing file {doc_file.filename} in session {session_id}")
                extracted_text, base64_image = _process_single_file(doc_file, model, is_vision)
                
                if is_image_file(doc_file.filepath) and is_vision:
                    vision_images.append(base64_image)
                
                doc_file.status = 'ready'
                doc_file.base64_image = base64_image
                doc_file.extracted_text = extracted_text
                db.session.add(doc_file)
                
                if extracted_text and extracted_text != "[Image analyzed via vision model]":
                    all_text_chunks.append(
                        f"--- Bắt đầu tệp: {doc_file.filename} ---\n"
                        f"{extracted_text}\n"
                        f"--- Kết thúc tệp: {doc_file.filename} ---"
                    )
                    
            except Exception as e:
                logging.exception(f"Error processing file {doc_file.filename}: {e}")
                doc_file.status = 'failed'
                doc_file.error_message = str(e)
                db.session.add(doc_file)
        
        try:
            db.session.commit()
        except Exception as commit_err:
            logging.exception(f"DB commit failed after file processing: {commit_err}")
            db.session.rollback()
        
        # Now update the aggregate session status
        failed_files = [f for f in doc_files if f.status == 'failed']
        if len(failed_files) == len(doc_files):
            raise Exception("Tất cả các tệp đều không xử lý được. / All files failed to process.")
        
        # Index document content into Vector DB for RAG if we have text chunks
        if all_text_chunks:
            combined_text = "\n\n".join(all_text_chunks)
            num_chunks = index_document(session_id, combined_text)
            logging.info(f"Successfully chunked and indexed {num_chunks} chunks for session {session_id}")
        
        # Formulate greeting
        greeting = _build_greeting(doc_files, len(vision_images), language)
        
        # Update database record
        session.status = 'ready'
        # Save first successful file preview for backward compatibility
        ready_files = [f for f in doc_files if f.status == 'ready']
        if ready_files:
            session.base64_image = ready_files[0].base64_image
            session.extracted_text = ready_files[0].extracted_text
        
        db.session.add(session)
        
        # Add greeting message to chat history
        greeting_msg = ChatMessage(session_id=session_id, role='assistant', content=greeting)
        db.session.add(greeting_msg)
        
        db.session.commit()
        logging.info(f"Session {session_id} is ready.")
        
    except Exception as e:
        logging.exception(f"Error occurred in process_document_task: {e}")
        try:
            session = DocumentSession.query.get(session_id)
            if session:
                session.status = 'failed'
                session.error_message = str(e)
                db.session.add(session)
                db.session.commit()
        except Exception as fallback_err:
            logging.exception(f"Failed to update session status on error: {fallback_err}")
            db.session.rollback()
