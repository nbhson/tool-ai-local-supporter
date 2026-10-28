import os
import re

import chromadb
import requests
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config

# Initialize local ChromaDB persistent client
CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

# Persistent session for connection pooling
rag_session = requests.Session()

_fastembed_model = None

def get_embedding_model():
    global _fastembed_model
    if _fastembed_model is None:
        from fastembed import TextEmbedding
        _fastembed_model = TextEmbedding(model_name=config.FASTEMBED_MODEL)
    return _fastembed_model

def get_ollama_embedding(text, model=None):
    """Generate embeddings for text using fastembed on CPU. Falls back to Ollama if fastembed fails."""
    try:
        model_instance = get_embedding_model()
        embeddings = list(model_instance.embed([text]))
        if embeddings:
            return [float(x) for x in embeddings[0]]
    except Exception as e:
        print(f"fastembed error: {e}. Falling back to Ollama API.")
        
    model = model or config.EMBEDDING_MODEL
    url = f"{config.OLLAMA_URL.rstrip('/')}/embeddings"
    
    try:
        response = rag_session.post(
            url,
            json={"model": model, "prompt": text, "keep_alive": "15m"},
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("embedding")
    except Exception as e:
        print(f"Error generating embedding in fallback Ollama: {e}")
        return None

def get_ollama_embeddings_batch(texts, model=None):
    """Generate embeddings for a list of texts using fastembed batching. Falls back to Ollama API."""
    if not texts:
        return []
    try:
        model_instance = get_embedding_model()
        embeddings = list(model_instance.embed(texts))
        return [[float(x) for x in emb] for emb in embeddings]
    except Exception as e:
        print(f"fastembed batch error: {e}. Falling back to Ollama API.")
        
    model = model or config.EMBEDDING_MODEL
    url = f"{config.OLLAMA_URL.rstrip('/')}/embed"
    
    try:
        response = rag_session.post(
            url,
            json={"model": model, "input": texts, "keep_alive": "15m"},
            timeout=60
        )
        response.raise_for_status()
        return response.json().get("embeddings", [])
    except Exception as e:
        print(f"Error generating batch embedding fallback Ollama: {e}. Falling back to sequential embeddings.")
        embeddings = []
        for t in texts:
            vector = get_ollama_embedding(t, model)
            embeddings.append(vector)
        return embeddings

def _code_aware_split(text, chunk_size=None, chunk_overlap=None):
    """Split text using code-aware boundaries when possible.
    
    Attempts to split at meaningful code boundaries (function/class/module)
    before falling back to recursive character splitting.
    """
    if chunk_size is None:
        chunk_size = config.RAG_CHUNK_SIZE
    if chunk_overlap is None:
        chunk_overlap = config.RAG_CHUNK_OVERLAP
    
    # Detect if this is primarily code content
    code_indicators = ['def ', 'class ', 'function ', 'import ', 'from ',
                       'const ', 'let ', 'var ', 'export ', 'async ',
                       'public ', 'private ', 'protected ', 'interface ']
    code_lines = sum(1 for line in text.split('\n')
                     if any(ind in line for ind in code_indicators))
    total_lines = len(text.split('\n'))
    is_code = total_lines > 0 and (code_lines / total_lines) > 0.15
    
    if not is_code or total_lines < 20:
        # For non-code or very short text, use standard splitting
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        return text_splitter.split_text(text)
    
    # Code-aware splitting: break at function/class boundaries
    boundaries = []
    boundary_patterns = [
        r'^(?:def |class |async def )',              # Python
        r'^(?:function |class |export (?:default )?(?:function|class))',  # JS/TS
        r'^(?:func |type |interface |struct )',        # Go
        r'^(?:pub (?:fn|struct|enum|impl|trait) )',   # Rust
        r'^(?:@Component|@Injectable|@NgModule)',       # Angular
    ]
    
    lines = text.split('\n')
    for i, line in enumerate(lines):
        for pattern in boundary_patterns:
            if re.match(pattern, line.strip()):
                boundaries.append(i)
                break
    
    # If no boundaries found, fall back to standard splitting
    if len(boundaries) < 2:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        return text_splitter.split_text(text)
    
    # Split at boundaries, respecting chunk_size
    chunks = []
    for i in range(len(boundaries)):
        start = boundaries[i]
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(lines)
        block = '\n'.join(lines[start:end])
        
        # If block exceeds chunk_size, sub-split it
        if len(block) > chunk_size:
            sub_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            chunks.extend(sub_splitter.split_text(block))
        elif block.strip():
            chunks.append(block)
    
    # If gaps exist between boundaries, also capture those
    if boundaries[0] > 0:
        preamble = '\n'.join(lines[:boundaries[0]]).strip()
        if preamble:
            chunks.insert(0, preamble)
    
    return chunks


def index_document(session_id, text):
    """Split text into chunks, generate embeddings, and store in ChromaDB."""
    if not text or not text.strip():
        return 0
    
    # 1. Split text into chunks (code-aware)
    chunks = _code_aware_split(text)
    chunks = [c for c in chunks if c.strip()]
    if not chunks:
        return 0
    
    # 2. Get or create collection for this session
    collection_name = f"sess_{session_id}"
    collection = chroma_client.get_or_create_collection(name=collection_name)
    
    # 3. Store chunks and embeddings in batches
    documents = []
    embeddings = []
    ids = []
    
    batch_size = 32
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i+batch_size]
        batch_vectors = get_ollama_embeddings_batch(batch_chunks)
        
        # Align chunks and vectors properly
        for idx, (chunk, vector) in enumerate(zip(batch_chunks, batch_vectors)):
            if vector:
                documents.append(chunk)
                embeddings.append(vector)
                ids.append(f"chunk_{i + idx}")
            
    if ids:
        collection.add(
            documents=documents,
            embeddings=embeddings,
            ids=ids
        )
    return len(ids)

def _keyword_search(texts, query, top_k=5):
    """Simple BM25-inspired keyword scoring for a list of text chunks.
    Returns (indices, scores) sorted by relevance descending."""
    if not texts or not query:
        return [], []
    
    # Tokenize query
    query_tokens = re.findall(r'\w+', query.lower())
    if not query_tokens:
        return [], []
    
    scores = []
    for i, text in enumerate(texts):
        text_lower = text.lower()
        text_tokens = set(re.findall(r'\w+', text_lower))
        text_len = max(len(text_tokens), 1)
        
        score = 0.0
        for token in query_tokens:
            # Term frequency (log-scaled)
            tf = text_lower.count(token)
            if tf > 0:
                import math
                score += (1 + math.log(tf)) * (1 / text_len)
        scores.append(score)
    
    # Sort by score descending
    indexed = sorted(enumerate(scores), key=lambda x: -x[1])
    # Filter out zero scores
    indexed = [(i, s) for i, s in indexed if s > 0]
    
    indices = [i for i, s in indexed[:top_k]]
    score_vals = [s for i, s in indexed[:top_k]]
    return indices, score_vals


def retrieve_context(session_id, query, top_k=None):
    """Find the most similar chunks using hybrid search (vector + keyword).
    
    Combines semantic vector similarity with BM25-inspired keyword matching
    for more robust retrieval.
    """
    if top_k is None:
        top_k = config.RAG_TOP_K
    
    try:
        collection_name = f"sess_{session_id}"
        collection = chroma_client.get_collection(name=collection_name)
        
        # Get total chunk count to decide strategy
        total = collection.count()
        if total == 0:
            return ""
        
        # Phase 1: Vector search — retrieve more candidates for re-ranking
        vector_candidates = min(top_k * 3, total)
        query_vector = get_ollama_embedding(query)
        
        vector_results = {}
        if query_vector:
            try:
                results = collection.query(
                    query_embeddings=[query_vector],
                    n_results=vector_candidates
                )
                docs = results.get('documents', [[]])[0]
                distances = results.get('distances', [[]])[0]
                for doc, dist in zip(docs, distances):
                    vector_results[doc] = 1.0 / (1.0 + dist)  # Convert distance to similarity score
            except Exception as e:
                print(f"Vector search error: {e}")
        
        # Phase 2: Keyword search on the same collection
        all_docs = []
        try:
            all_results = collection.get(include=["documents"])
            all_docs = all_results.get('documents', [])
        except Exception as e:
            print(f"Error getting all docs for keyword search: {e}")
        
        keyword_indices, keyword_scores = _keyword_search(all_docs, query, top_k=top_k * 2)
        keyword_results = {}
        if keyword_indices:
            max_kw_score = max(keyword_scores) if keyword_scores else 1.0
            for idx, score in zip(keyword_indices, keyword_scores):
                if idx < len(all_docs):
                    keyword_results[all_docs[idx]] = score / max_kw_score  # Normalize to 0-1
        
        # Phase 3: Reciprocal Rank Fusion (RRF)
        # Combine scores from both methods
        combined_scores = {}
        for doc in set(list(vector_results.keys()) + list(keyword_results.keys())):
            vs = vector_results.get(doc, 0.0)
            ks = keyword_results.get(doc, 0.0)
            # Weighted combination: 60% vector + 40% keyword
            combined_scores[doc] = 0.6 * vs + 0.4 * ks
        
        # Sort by combined score and take top_k
        sorted_docs = sorted(combined_scores.items(), key=lambda x: -x[1])[:top_k]
        final_docs = [doc for doc, score in sorted_docs if score > 0]
        
        return "\n\n---\n\n".join(final_docs) if final_docs else ""
    except Exception as e:
        print(f"Error retrieving context for session {session_id}: {e}")
        return ""

