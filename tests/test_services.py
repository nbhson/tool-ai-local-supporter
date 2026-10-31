"""Unit tests for service-layer logic (helper, RAG, agent tools, tasks)."""

from types import SimpleNamespace

import pytest

from services.agent_service import parse_all_tool_calls, scan_directory_and_stats
from services.agent_tool_service import ToolRegistry
from services.document_service import (
    extract_text_from_file,
    extract_text_from_image_ocr,
    resize_and_compress_image,
)
from services.extractor_service import ExtractorFactory
from services.helper_service import (
    _summarize_old_messages,
    parse_ollama_sse_chunk,
)
from services.rag_service import _code_aware_split, _keyword_search
from tasks import DocumentProcessingError, _build_greeting

# ---------------------------------------------------------------------------
# helper_service
# ---------------------------------------------------------------------------


def test_parse_ollama_sse_chunk_content():
    chunk = 'data: {"content": "hello"}\n\n'
    assert parse_ollama_sse_chunk(chunk) == {"content": "hello"}


def test_parse_ollama_sse_chunk_done_sentinel():
    assert parse_ollama_sse_chunk("data: [DONE]\n\n") is None


def test_parse_ollama_sse_chunk_invalid_json():
    assert parse_ollama_sse_chunk("data: {broken json") is None


def test_parse_ollama_sse_chunk_non_data_line():
    assert parse_ollama_sse_chunk(": keep-alive padding\n") is None


def test_summarize_old_messages_short_history_unchanged():
    messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    assert _summarize_old_messages(messages) == messages


def test_summarize_old_messages_long_history_compacted():
    messages = [{"role": "user", "content": f"question {i}"} for i in range(6)]
    messages += [{"role": "assistant", "content": f"answer {i}"} for i in range(3)]
    result = _summarize_old_messages(messages)

    # 2 synthetic summary messages + last 3 kept in full
    assert len(result) == 5
    assert result[0]["role"] == "user"
    assert "summary of earlier messages" in result[0]["content"]
    assert result[1]["role"] == "assistant"
    assert result[2:] == messages[-3:]


def test_summarize_old_messages_truncates_long_content():
    long_msg = {"role": "user", "content": "x" * 300}
    messages = [long_msg] + [{"role": "assistant", "content": f"m{i}"} for i in range(5)]
    result = _summarize_old_messages(messages)
    summary_text = result[0]["content"]
    assert "xxx..." in summary_text
    assert len(summary_text) < len(long_msg["content"])


# ---------------------------------------------------------------------------
# rag_service — pure helpers
# ---------------------------------------------------------------------------


def test_code_aware_split_short_text_uses_recursive_splitter():
    text = "just a plain paragraph. " * 30
    chunks = _code_aware_split(text, chunk_size=200, chunk_overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 400 for c in chunks)


def test_code_aware_split_python_code_at_boundaries():
    # Keep indicator density above the 15% code-detection threshold
    code = "\n".join(f"def function_{i}():" + "\n    pass" * 5 for i in range(20))
    chunks = _code_aware_split(code, chunk_size=100000, chunk_overlap=0)
    # Each def block should start its own chunk
    starts = [c.strip().startswith("def ") for c in chunks]
    assert sum(starts) >= 3


def test_keyword_search_ranks_relevant_chunk_first():
    texts = [
        "The quick brown fox jumps over the lazy dog.",
        "Flask is a micro web framework written in Python.",
        "Completely unrelated content about gardening and flowers.",
    ]
    indices, scores = _keyword_search(texts, "flask web framework", top_k=2)
    assert indices[0] == 1
    assert scores[0] > 0
    assert len(indices) <= 2


def test_keyword_search_empty_inputs():
    assert _keyword_search([], "query") == ([], [])
    assert _keyword_search(["text"], "") == ([], [])


def test_keyword_search_no_match_returns_empty():
    indices, scores = _keyword_search(["hello world"], "zebra")
    assert indices == []
    assert scores == []


# ---------------------------------------------------------------------------
# agent_service — directory scanning
# ---------------------------------------------------------------------------


def test_scan_directory_and_stats_skips_excluded_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-314.pyc").write_bytes(b"\x00")
    (tmp_path / ".DS_Store").write_bytes(b"\x00")

    tree, stats = scan_directory_and_stats(str(tmp_path), str(tmp_path))

    names = [n["name"] for n in tree]
    assert "src" in names
    assert "__pycache__" not in names
    assert stats["total_files"] == 1
    assert stats["lang_stats"] == {"py": 1}


def test_scan_directory_and_stats_respects_max_depth(tmp_path):
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)
    (tmp_path / "a" / "b" / "c" / "deep.py").write_text("x")

    tree, _ = scan_directory_and_stats(str(tmp_path), str(tmp_path), max_depth=1)
    # depth 1 shows "a" and its direct children, but not deeper levels
    child = tree[0]["children"][0]
    assert child["name"] == "b"
    assert child["children"] == []


def test_parse_all_tool_calls_multiple_tools():
    text = """Let me inspect.
[READ_FILE: a.py]
[LIST_DIR: .]
[RUN_COMMAND: git status]
"""
    calls = parse_all_tool_calls(text)
    tools = [c["tool"] for c in calls]
    assert tools == ["READ_FILE", "LIST_DIR", "RUN_COMMAND"]
    assert calls[0]["args"] == {"path": "a.py"}
    assert calls[2]["args"] == {"command": "git status"}


def test_parse_all_tool_calls_regex_search_with_file_pattern():
    calls = parse_all_tool_calls("[REGEX_SEARCH: def main | *.py]")
    assert calls == [{"tool": "REGEX_SEARCH", "args": {"pattern": "def main", "file_pattern": "*.py"}}]


def test_parse_all_tool_calls_edit_file_payload():
    text = """[EDIT_FILE: src/app.py]
<<<SEARCH>>>old = 1<<<END_SEARCH>>>
<<<REPLACE>>>new = 2<<<END_REPLACE>>>
"""
    calls = parse_all_tool_calls(text)
    assert calls[0]["tool"] == "EDIT_FILE"
    assert calls[0]["args"]["path"] == "src/app.py"
    assert calls[0]["args"]["search"] == "old = 1"
    assert calls[0]["args"]["replace"] == "new = 2"


# ---------------------------------------------------------------------------
# agent_tool_service — file tools via ToolRegistry
# ---------------------------------------------------------------------------


def test_read_file_tool_returns_content(tmp_path):
    (tmp_path / "note.txt").write_text("hello world")
    result = ToolRegistry.execute_tool("READ_FILE", {"path": "note.txt"}, str(tmp_path))
    assert "hello world" in result
    assert "note.txt" in result


def test_read_file_tool_rejects_traversal(tmp_path):
    result = ToolRegistry.execute_tool("READ_FILE", {"path": "../outside.txt"}, str(tmp_path))
    assert result.startswith("Error:")


def test_write_and_edit_file_tool_roundtrip(tmp_path):
    ToolRegistry.execute_tool("WRITE_FILE", {"path": "src/app.py", "content": "old = 1\n"}, str(tmp_path))
    assert (tmp_path / "src" / "app.py").read_text() == "old = 1\n"

    result = ToolRegistry.execute_tool(
        "EDIT_FILE",
        {"path": "src/app.py", "search": "old = 1", "replace": "new = 2"},
        str(tmp_path),
    )
    assert result.startswith("Success")
    assert (tmp_path / "src" / "app.py").read_text() == "new = 2\n"


def test_edit_file_tool_rejects_ambiguous_search(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\ny = 1\n")
    result = ToolRegistry.execute_tool(
        "EDIT_FILE", {"path": "app.py", "search": "= 1", "replace": "= 2"}, str(tmp_path)
    )
    assert "found 2 times" in result


def test_edit_file_tool_rejects_missing_search(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    result = ToolRegistry.execute_tool(
        "EDIT_FILE", {"path": "app.py", "search": "not present", "replace": "y"}, str(tmp_path)
    )
    assert "Search string not found" in result


def test_list_dir_tool_excludes_junk(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x")
    (tmp_path / "readme.txt").write_text("r")
    (tmp_path / ".DS_Store").write_bytes(b"\x00")
    result = ToolRegistry.execute_tool("LIST_DIR", {"path": "."}, str(tmp_path))
    assert "[DIR] src" in result
    assert "[FILE] readme.txt" in result
    assert ".DS_Store" not in result


def test_regex_search_tool_matches_lines(tmp_path):
    (tmp_path / "app.py").write_text("def main():\n    pass\n")
    result = ToolRegistry.execute_tool(
        "REGEX_SEARCH", {"pattern": r"def \w+", "file_pattern": r".*\.py"}, str(tmp_path)
    )
    assert "app.py:1: def main():" in result


def test_regex_search_tool_rejects_invalid_pattern(tmp_path):
    result = ToolRegistry.execute_tool("REGEX_SEARCH", {"pattern": "("}, str(tmp_path))
    assert "Invalid regex pattern" in result


# ---------------------------------------------------------------------------
# document_service / extractor_service
# ---------------------------------------------------------------------------


def test_extract_text_from_file_txt(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("nội dung văn bản")
    assert extract_text_from_file(str(f)) == "nội dung văn bản"


def test_extract_text_from_file_returns_none_for_image(tmp_path):
    f = tmp_path / "img.png"
    f.write_bytes(b"fake")
    assert extract_text_from_file(str(f)) is None


def test_extractor_factory_maps_extensions():
    assert ExtractorFactory.get_extractor("a.pdf") is not None
    assert ExtractorFactory.get_extractor("b.docx") is not None
    assert ExtractorFactory.get_extractor("c.txt") is not None
    assert ExtractorFactory.get_extractor("d.unknownext") is None


def test_extract_text_from_image_ocr_broken_image(tmp_path):
    # Without a valid raster image this returns an OCR error string or None,
    # but must never raise.
    f = tmp_path / "broken.png"
    f.write_bytes(b"not an image")
    result = extract_text_from_image_ocr(str(f))
    assert result is None or result.startswith("OCR Error")


def test_resize_and_compress_image(tmp_path):
    import base64 as _b64

    from PIL import Image

    img = Image.new("RGB", (3000, 2000), color=(120, 40, 200))
    f = tmp_path / "big.png"
    img.save(str(f), format="PNG")

    b64 = resize_and_compress_image(str(f))
    assert b64 is not None
    raw = _b64.b64decode(b64)
    assert raw[:2] == b"\xff\xd8"  # JPEG magic bytes


def test_resize_and_compress_image_invalid_file(tmp_path):
    f = tmp_path / "bad.png"
    f.write_bytes(b"garbage")
    assert resize_and_compress_image(str(f)) is None


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------


def _fake_doc_file(tmp_path, name="a.txt"):
    return SimpleNamespace(
        filename=name,
        filepath=str(tmp_path / name),
        status="processing",
        base64_image=None,
        extracted_text=None,
        error_message=None,
    )


def test_build_greeting_vision_vi(tmp_path):
    msg = _build_greeting([_fake_doc_file(tmp_path)], vision_images_count=2, language="vi")
    assert "2 hình ảnh" in msg


def test_build_greeting_documents_en(tmp_path):
    msg = _build_greeting([_fake_doc_file(tmp_path)], vision_images_count=0, language="en")
    assert "analyzed 1 documents" in msg


def test_build_greeting_truncates_long_filenames(tmp_path):
    files = [_fake_doc_file(tmp_path, "very_long_filename_" + "x" * 80 + ".txt")]
    msg = _build_greeting(files, vision_images_count=0, language="en")
    assert "..." in msg


def test_process_single_file_text_document(tmp_path):
    from tasks import _process_single_file

    f = tmp_path / "doc.txt"
    f.write_text("plain text content")
    doc = _fake_doc_file(tmp_path)
    doc.filepath = str(f)

    text, b64 = _process_single_file(doc, model="test-model", is_vision=False)
    assert text == "plain text content"
    assert b64 is None


def test_process_single_file_raises_on_extraction_error(tmp_path):
    from tasks import _process_single_file

    # .pdf with invalid bytes → pypdf error string starting with "Error"
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"not a real pdf")
    doc = _fake_doc_file(tmp_path)
    doc.filepath = str(f)

    with pytest.raises(DocumentProcessingError):
        _process_single_file(doc, model="test-model", is_vision=False)


def test_process_single_file_image_non_vision_model_ocr_fallback(tmp_path):
    from PIL import Image

    from tasks import _process_single_file

    img = Image.new("RGB", (200, 100), color="white")
    f = tmp_path / "pic.png"
    img.save(str(f), format="PNG")
    doc = _fake_doc_file(tmp_path)
    doc.filepath = str(f)

    text, b64 = _process_single_file(doc, model="test-model", is_vision=False)
    # OCR may find no text → placeholder message; must not raise
    assert isinstance(text, str)
    assert b64  # base64 image is always produced for images


# ---------------------------------------------------------------------------
# config sanity
# ---------------------------------------------------------------------------


def test_config_hybrid_weights_sum_to_one():
    import config

    assert pytest.approx(1.0) == config.RAG_HYBRID_VECTOR_WEIGHT + config.RAG_HYBRID_KEYWORD_WEIGHT
