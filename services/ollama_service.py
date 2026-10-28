import json
import time

import requests

import config
from services.logger import log

# Create a persistent session for HTTP connection pooling to Ollama API
ollama_session = requests.Session()

def is_vision_model(model_name):
    """Check if model supports vision/multimodal."""
    model_lower = model_name.lower()
    return any(vm in model_lower for vm in config.VISION_MODELS)

def call_ollama(messages, model=None, stream=False):
    model = model or config.DEFAULT_MODEL
    log.ollama_request(model, len(messages), stream=stream)

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "keep_alive": "15m",
        "options": {
            "temperature": 0.2,
            "num_predict": 4096,
            "num_ctx": config.OLLAMA_NUM_CTX
        }
    }

    def generate_error(msg):
        log.error(f"Ollama error response: {msg}")
        yield f"data: {json.dumps({'error': msg})}\n\n"
        yield "data: [DONE]\n\n"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            log.debug(f"POST {config.OLLAMA_URL}/chat (attempt {attempt + 1}/{max_retries})")
            req_start = time.time()
            response = ollama_session.post(
                f"{config.OLLAMA_URL}/chat", json=payload, timeout=(10, 600), stream=stream
            )
            req_ms = (time.time() - req_start) * 1000

            if response.status_code != 200:
                error_detail = response.text
                log.ollama_error(response.status_code, error_detail)
                err_msg = f"Ollama API error {response.status_code}: {error_detail}"
                return generate_error(err_msg) if stream else {"error": err_msg}

            log.debug(f"Ollama responded {response.status_code} in {req_ms:.0f}ms")

            if stream:
                def generate():
                    chunk_count = 0
                    for line in response.iter_lines():
                        if line:
                            try:
                                chunk = json.loads(line.decode('utf-8'))
                                content = chunk.get("message", {}).get("content", "")
                                if content:
                                    chunk_count += 1
                                    yield f"data: {json.dumps({'content': content})}\n\n"
                            except Exception as e:
                                log.warning(f"Error parsing Ollama chunk: {e}")
                    log.debug(f"Stream complete: {chunk_count} chunks received")
                    yield "data: [DONE]\n\n"
                return generate()
            else:
                return response.json()
        except requests.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                log.ollama_retry(attempt, max_retries, "Connection refused")
                time.sleep(2 ** attempt)
            else:
                log.error(f"Failed to connect to Ollama after {max_retries} attempts.")
                err_msg = "Cannot connect to Ollama. Make sure Ollama is running"
                return generate_error(err_msg) if stream else {"error": err_msg}
        except requests.exceptions.Timeout:
            log.ollama_error("TIMEOUT", "Request timed out after 600s")
            err_msg = "Request timed out."
            return generate_error(err_msg) if stream else {"error": err_msg}
        except Exception as e:
            log.error(f"Unexpected error in call_ollama: {e}")
            err_msg = f"Ollama error: {e!s}"
            return generate_error(err_msg) if stream else {"error": err_msg}


def analyze_with_ollama(text, filename, model=None, content_type="document", language="en"):
    """Send text content to Ollama for initial analysis."""
    model = model or config.DEFAULT_MODEL
    max_chars = config.MAX_TEXT_CHARS
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n...[truncated]"


    # Determine language instruction
    lang_instruction = "Respond in English." if language == "en" else "Respond in Vietnamese."

    if content_type == "code":
        system_prompt = f"""You are a code analysis assistant. Analyze the provided code and provide:
1. The programming language and overall purpose
2. Key components (functions, classes, modules)
3. Notable patterns, potential issues, or improvements
4. How the code works at a high level
Be technical and precise. {lang_instruction}"""
        user_prompt = f"""Please analyze this code (filename: {filename}):
---
{text}
---"""
    else:
        system_prompt = f"""You are a document analysis assistant. Analyze the document and extract key information.
Summarize and highlight important points, data, and insights. {lang_instruction}"""
        user_prompt = f"""Please analyze this document (filename: {filename}):
---
{text}
---"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    return call_ollama(messages, model)


