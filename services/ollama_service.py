"""Ollama HTTP client with connection pooling, retries and SSE streaming."""

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
                def generate(resp):
                    chunk_count = 0
                    for line in resp.iter_lines():
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
                return generate(response)
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


