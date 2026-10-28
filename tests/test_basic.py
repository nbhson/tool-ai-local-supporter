import pytest

from services.agent_service import get_simple_tree_str, parse_tool_call
from services.document_service import allowed_file, is_image_file
from services.ollama_service import is_vision_model


def test_allowed_file():
    assert allowed_file("test.pdf") is True
    assert allowed_file("test.docx") is True
    assert allowed_file("test.png") is True
    assert allowed_file("test.invalid_ext") is False

def test_is_image_file():
    assert is_image_file("test.png") is True
    assert is_image_file("test.jpg") is True
    assert is_image_file("test.pdf") is False

def test_is_vision_model():
    assert is_vision_model("qwen2.5-vl") is True
    assert is_vision_model("llava") is True
    assert is_vision_model("qwen2.5-coder:14b") is False

def test_parse_tool_call():
    # Test [FINISH]
    assert parse_tool_call("Let's end this [FINISH]") == {'tool': 'FINISH', 'args': {}}

    # Test [READ_FILE: path]
    assert parse_tool_call("Read the config [READ_FILE: config.py]") == {
        'tool': 'READ_FILE', 'args': {'path': 'config.py'}
    }

    # Test [LIST_DIR: path]
    assert parse_tool_call("List files: [LIST_DIR: .]") == {
        'tool': 'LIST_DIR', 'args': {'path': '.'}
    }

    # Test [SEARCH_FILES: query]
    assert parse_tool_call("Search query: [SEARCH_FILES: my query]") == {
        'tool': 'SEARCH_FILES', 'args': {'query': 'my query'}
    }

    # Test [RUN_COMMAND: cmd]
    assert parse_tool_call("Run command: [RUN_COMMAND: ls -la]") == {
        'tool': 'RUN_COMMAND', 'args': {'command': 'ls -la'}
    }

    # Test [WRITE_FILE: path] with markdown
    write_input = """Write file [WRITE_FILE: test.py]
```python
def main():
    print("hello")
```"""
    res = parse_tool_call(write_input)
    assert res is not None
    assert res['tool'] == 'WRITE_FILE'
    assert res['args']['path'] == 'test.py'
    assert "def main():" in res['args']['content']

def test_get_simple_tree_str():
    nodes = [
        {"name": "app.py", "is_dir": False},
        {"name": "services", "is_dir": True, "children": [
            {"name": "database.py", "is_dir": False}
        ]}
    ]
    lines = get_simple_tree_str(nodes)
    assert len(lines) >= 2
    assert any("app.py" in line for line in lines)
    assert any("services" in line for line in lines)

def test_helper_service():
    from services.helper_service import format_sse_event, get_lang_instruction
    assert get_lang_instruction("en") == "Respond in English."
    assert get_lang_instruction("vi") == "Respond in Vietnamese."
    
    sse_str = format_sse_event("test_event", val="hello")
    assert "data: " in sse_str
    assert "test_event" in sse_str
    assert "hello" in sse_str

def test_agent_tools():
    from services.agent_tool_service import ToolRegistry
    # Test unknown tool
    assert "Error: Unknown tool" in ToolRegistry.execute_tool("UNKNOWN_TOOL", {}, ".")
    
    # Test READ_FILE error case
    assert "Error: File not found" in ToolRegistry.execute_tool("READ_FILE", {"path": "non_existent.txt"}, ".")

def test_safe_join_project_path():
    import os

    from services.helper_service import safe_join_project_path
    base = os.path.abspath(".")
    
    # Valid join
    assert safe_join_project_path(base, "app.py") == os.path.join(base, "app.py")
    assert safe_join_project_path(base, "services/helper_service.py") == os.path.join(base, "services/helper_service.py")
    
    # Invalid joins (path traversal)
    with pytest.raises(ValueError):
        safe_join_project_path(base, "../outside.txt")
        
    with pytest.raises(ValueError):
        safe_join_project_path(base, "/etc/passwd")

def test_project_tree_cache():
    from services.agent_service import (
        get_cached_project_tree,
        invalidate_project_tree_cache,
        set_cached_project_tree,
    )
    session_id = "test_session_123"
    
    # Initially cache should be empty
    tree, stats = get_cached_project_tree(session_id)
    assert tree is None
    assert stats is None
    
    # Store in cache
    dummy_tree = [{"name": "file.py", "is_dir": False}]
    dummy_stats = {"total_files": 1, "total_size": 100, "lang_stats": {"py": 1}}
    set_cached_project_tree(session_id, dummy_tree, dummy_stats)
    
    # Retrieve from cache
    cached_tree, cached_stats = get_cached_project_tree(session_id)
    assert cached_tree == dummy_tree
    assert cached_stats == dummy_stats
    
    # Invalidate cache
    invalidate_project_tree_cache(session_id)
    cached_tree, cached_stats = get_cached_project_tree(session_id)
    assert cached_tree is None
    assert cached_stats is None



