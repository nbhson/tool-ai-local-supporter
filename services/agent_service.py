import json
import logging
import os
import re
import time

import config
from services.helper_service import (
    format_sse_event,
    get_lang_instruction,
    retrieve_chat_history,
    save_chat_message,
)
from services.logger import log
from services.ollama_service import call_ollama

# In-memory cache for project tree with TTL (prevents unbounded memory growth)
# Format: session_id -> {"tree": tree, "stats": stats, "timestamp": float}
_project_tree_cache = {}
_PROJECT_TREE_CACHE_TTL = 300  # 5 minutes

def get_cached_project_tree(session_id):
    """Retrieve the cached project tree and stats for a session (with TTL expiry)."""
    cache_entry = _project_tree_cache.get(session_id)
    if cache_entry:
        if time.time() - cache_entry["timestamp"] < _PROJECT_TREE_CACHE_TTL:
            return cache_entry["tree"], cache_entry["stats"]
        # Expired — evict
        del _project_tree_cache[session_id]
    return None, None

def set_cached_project_tree(session_id, tree, stats):
    """Cache the project tree and stats for a session."""
    _project_tree_cache[session_id] = {
        "tree": tree,
        "stats": stats,
        "timestamp": time.time()
    }

def invalidate_project_tree_cache(session_id):
    """Invalidate/delete the cached project tree for a session."""
    _project_tree_cache.pop(session_id, None)

def scan_directory_and_stats(current_path, base_path, stats=None, current_depth=0, max_depth=None):
    if stats is None:
        stats = {
            "total_files": 0,
            "total_size": 0,
            "lang_stats": {}
        }
    tree = []
    if max_depth is not None and current_depth > max_depth:
        return tree, stats
    try:
        entries = sorted(os.scandir(current_path), key=lambda e: (not e.is_dir(), e.name.lower()))
        for entry in entries:
            if entry.is_dir():
                if entry.name in config.EXCLUDE_DIRS:
                    continue
                subtree, _ = scan_directory_and_stats(entry.path, base_path, stats, current_depth + 1, max_depth)
                tree.append({
                    "name": entry.name,
                    "path": os.path.relpath(entry.path, base_path),
                    "is_dir": True,
                    "children": subtree
                })
            else:
                if entry.name in config.EXCLUDE_FILES:
                    continue
                rel_path = os.path.relpath(entry.path, base_path)
                tree.append({
                    "name": entry.name,
                    "path": rel_path,
                    "is_dir": False
                })
                try:
                    size = entry.stat().st_size
                    stats["total_size"] += size
                    stats["total_files"] += 1
                    
                    _, ext = os.path.splitext(entry.name)
                    ext = ext.lower().strip('.')
                    if not ext:
                        ext = 'plain text' if entry.name.startswith('.') or entry.name in ('LICENSE', 'Makefile', 'Dockerfile') else 'unknown'
                    stats["lang_stats"][ext] = stats["lang_stats"].get(ext, 0) + 1
                except Exception:
                    pass
    except Exception as e:
        logging.error(f"Error scanning directory {current_path}: {e}")
    return tree, stats

def _compute_file_importance(node, base_importance=0):
    """Compute an importance score for a file node based on heuristics."""
    name = node.get('name', '').lower()
    score = base_importance
    # Config / entry files are important
    if name in ('package.json', 'requirements.txt', 'pyproject.toml', 'setup.py', 'setup.cfg',
                'go.mod', 'cargo.toml', 'dockerfile', 'docker-compose.yml', 'docker-compose.yaml',
                'readme.md', 'makefile', '.env.example', 'tsconfig.json', 'webpack.config.js',
                'vite.config.js', 'vite.config.ts', 'next.config.js', 'next.config.ts'):
        score += 3
    # Source files
    if any(name.endswith(ext) for ext in ('.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.java', '.rb', '.php')):
        score += 2
    # Test files (lower priority in overview)
    if name.startswith('test_') or name.endswith('_test.py') or name.endswith('.test.js') or name.endswith('.test.ts'):
        score -= 1
    return score


def get_simple_tree_str(nodes, depth=0, max_depth=None, max_entries_per_dir=None):
    if max_depth is None:
        max_depth = config.AGENT_MAX_DEPTH
    if max_entries_per_dir is None:
        max_entries_per_dir = config.AGENT_MAX_ENTRIES_PER_DIR
    if depth > max_depth:
        return []
    
    # Sort: directories first, then by importance score (descending)
    sorted_nodes = sorted(nodes, key=lambda n: (not n.get('is_dir', False), -_compute_file_importance(n)))
    
    lines = []
    for i, node in enumerate(sorted_nodes):
        if i >= max_entries_per_dir:
            lines.append(f"{'  ' * depth}... (and {len(sorted_nodes) - max_entries_per_dir} more items, use LIST_DIR tool to view)")
            break
            
        indent = "  " * depth
        if node.get("is_dir"):
            lines.append(f"{indent}📁 {node['name']}/")
            lines.extend(get_simple_tree_str(node.get("children", []), depth + 1, max_depth, max_entries_per_dir))
        else:
            lines.append(f"{indent}📄 {node['name']}")
    return lines

def parse_all_tool_calls(text):
    """
    Parses all tool calls from the assistant response text.
    Returns a list of dicts: [{'tool': tool_name, 'args': tool_args}]
    """
    tool_calls = []

    # Parse [FINISH] if present (should not short-circuit other tool calls)
    if '[FINISH]' in text:
        tool_calls.append({'tool': 'FINISH', 'args': {}})
    
    # Match simple tool tags: [TOOL: value]
    simple_pattern = r'\[(READ_FILE|LIST_DIR|SEARCH_FILES|RUN_COMMAND|GIT_DIFF|GIT_LOG|LINT_CODE):\s*([^\]\n]+)\]'
    simple_matches = list(re.finditer(simple_pattern, text))
    
    # Track positions that are already consumed by simple matches
    consumed_ranges = [(m.start(), m.end()) for m in simple_matches]
    
    for match in simple_matches:
        tool_name = match.group(1)
        arg_val = match.group(2).strip()
        
        if tool_name == 'READ_FILE':
            tool_calls.append({'tool': 'READ_FILE', 'args': {'path': arg_val}})
        elif tool_name == 'LIST_DIR':
            tool_calls.append({'tool': 'LIST_DIR', 'args': {'path': arg_val}})
        elif tool_name == 'SEARCH_FILES':
            tool_calls.append({'tool': 'SEARCH_FILES', 'args': {'query': arg_val}})
        elif tool_name == 'RUN_COMMAND':
            tool_calls.append({'tool': 'RUN_COMMAND', 'args': {'command': arg_val}})
        elif tool_name == 'GIT_DIFF':
            tool_calls.append({'tool': 'GIT_DIFF', 'args': {'path': arg_val}})
        elif tool_name == 'GIT_LOG':
            tool_calls.append({'tool': 'GIT_LOG', 'args': {'count': arg_val}})
        elif tool_name == 'LINT_CODE':
            tool_calls.append({'tool': 'LINT_CODE', 'args': {'command': arg_val}})
    
    # Match [RUN_TESTS: command] (optional command)
    rt_pattern = r'\[RUN_TESTS:\s*([^\]\n]*)\]'
    for match in re.finditer(rt_pattern, text):
        cmd = match.group(1).strip()
        tool_calls.append({'tool': 'RUN_TESTS', 'args': {'command': cmd}})
    
    # Match [REGEX_SEARCH: pattern] or [REGEX_SEARCH: pattern | file_pattern]
    rs_pattern = r'\[REGEX_SEARCH:\s*([^\]\n]+)\]'
    for match in re.finditer(rs_pattern, text):
        val = match.group(1).strip()
        parts = [p.strip() for p in val.split('|', 1)]
        args = {'pattern': parts[0]}
        if len(parts) > 1:
            args['file_pattern'] = parts[1]
        tool_calls.append({'tool': 'REGEX_SEARCH', 'args': args})
    
    # Match [EDIT_FILE: path]
    # Requires: search string in <<<>>> delimiters, replace in <<<>>> delimiters
    ef_pattern = r'\[EDIT_FILE:\s*([^\]\n]+)\]'
    all_matches_iter = list(re.finditer(ef_pattern, text))
    for match in all_matches_iter:
        file_path = match.group(1).strip()
        # Extract content after this match until next tool tag or end of text
        start_pos = match.end()
        # Find the next tool tag
        next_tag = re.search(r'\[(?:READ_FILE|WRITE_FILE|LIST_DIR|SEARCH_FILES|RUN_COMMAND|EDIT_FILE|GIT_DIFF|GIT_LOG|RUN_TESTS|LINT_CODE|REGEX_SEARCH|FINISH):', text[start_pos:])
        end_pos = start_pos + next_tag.start() if next_tag else len(text)
        segment = text[start_pos:end_pos]
        
        search_match = re.search(r'<<<SEARCH>>>([\s\S]*?)<<<END_SEARCH>>>', segment)
        replace_match = re.search(r'<<<REPLACE>>>([\s\S]*?)<<<END_REPLACE>>>', segment)
        
        search_str = search_match.group(1).strip() if search_match else ''
        replace_str = replace_match.group(1).strip() if replace_match else ''
        
        tool_calls.append({'tool': 'EDIT_FILE', 'args': {'path': file_path, 'search': search_str, 'replace': replace_str}})
    
    # Match [WRITE_FILE: path]
    wf_pattern = r'\[(WRITE_FILE):\s*([^\]\n]+)\]'
    wf_matches = list(re.finditer(wf_pattern, text))
    for match in wf_matches:
        file_path = match.group(2).strip()
        start_pos = match.end()
        # Find next tool tag
        next_tag = re.search(r'\[(?:READ_FILE|WRITE_FILE|LIST_DIR|SEARCH_FILES|RUN_COMMAND|EDIT_FILE|GIT_DIFF|GIT_LOG|RUN_TESTS|LINT_CODE|REGEX_SEARCH|FINISH):', text[start_pos:])
        end_pos = start_pos + next_tag.start() if next_tag else len(text)
        segment = text[start_pos:end_pos]
        
        # Extract code block if present
        code_block = re.search(r'```(?:\w*)\n([\s\S]*?)```', segment)
        if code_block:
            content = code_block.group(1)
        else:
            content = segment.strip()
        tool_calls.append({'tool': 'WRITE_FILE', 'args': {'path': file_path, 'content': content}})
            
    return tool_calls

def parse_tool_call(text):
    """Legacy parser for compatibility with tests."""
    calls = parse_all_tool_calls(text)
    return calls[0] if calls else None

from services.agent_tool_service import ToolRegistry


def execute_agent_tool(tool_name, args, project_path):
    return ToolRegistry.execute_tool(tool_name, args, project_path)

def generate_agent_stream(session_id, project_path, question, language, model, context_str, tree_str, agent_mode):
    """Executes the main ReAct software development agent loop, yielding SSE events."""
    from app import app
    with app.app_context():
        log.agent_start(session_id, question, model, agent_mode)
        log.info("Project path set", path=project_path, lang=language)

        lang_instruction = get_lang_instruction(language)
        
        if agent_mode:
            system_prompt = f"""You are a professional AI Software Engineering Agent helping the user work on a local project workspace.
You have direct read/write access to the files and can execute terminal commands within this directory.
{lang_instruction}

CURRENT DIRECTORY TREE STRUCTURE:
```
{tree_str}
```
{context_str}

YOUR WORKFLOW:
1. Understand the user's request.
2. Outline your plan of actions in your thought process.
3. Perform actions step-by-step using the following TOOL CALLS.
4. You can call multiple tools at the end of your response in parallel if you need to gather information or make changes to multiple files (e.g. read multiple files or write multiple files). Output all tool calls you want to execute in this turn together.
5. Once you have finished all tasks and verified them, output [FINISH] with a final explanation of the changes.

TOOL CALL SYNTAX:
To call a tool, you MUST output the exact tag format at the very end of your response:

- Read a file's content:
  [READ_FILE: path/to/file.ext]
- Edit a specific part of a file (PREFER this over WRITE_FILE for targeted changes):
  [EDIT_FILE: path/to/file.ext]
  <<<SEARCH>>>exact text to find<<<END_SEARCH>>>
  <<<REPLACE>>>replacement text<<<END_REPLACE>>>
- Write/overwrite a file (use only for new files or complete rewrites):
  [WRITE_FILE: path/to/file.ext]
  ```language
  // full code content
  ```
- List directory contents:
  [LIST_DIR: path/to/dir] (use "." for root)
- Search for keyword in filenames or contents:
  [SEARCH_FILES: keyword]
- Search using regex patterns:
  [REGEX_SEARCH: pattern] or [REGEX_SEARCH: pattern | file_pattern]
- Run a terminal command (e.g. compile, syntax check):
  [RUN_COMMAND: command]
- Run the project's test suite (auto-detects framework):
  [RUN_TESTS] or [RUN_TESTS: custom-command]
- Run linter on the project (auto-detects linter):
  [LINT_CODE] or [LINT_CODE: custom-command]
- View git diff (unstaged changes):
  [GIT_DIFF] or [GIT_DIFF: path/to/file]
- View recent git commits:
  [GIT_LOG] or [GIT_LOG: number_of_commits]
- Mark the task as fully completed:
  [FINISH]

RULES:
- When writing files, ALWAYS output the FULL file content in code block.
- PREFER [EDIT_FILE] over [WRITE_FILE] when making targeted changes to existing files. Only use [WRITE_FILE] for new files or complete rewrites.
- CRITICAL AUTO-APPLY: All file changes via [WRITE_FILE] and [EDIT_FILE] are applied automatically and immediately. Do NOT ask for user confirmation. Just make the changes directly.
- NEVER output code blocks (```) in your text response for file modifications. ALWAYS use [WRITE_FILE] or [EDIT_FILE] tool calls instead. Code blocks in your response text are for explanation/display only, NOT for applying changes.
- Paths must be relative to the project root (no leading '/').
- You can output multiple tool call tags at the end of your response when you need info or actions on multiple files.
- For thought process, keep it extremely concise (1-2 sentences) inside . For simple greetings or casual chat, SKIP the thought process and reply immediately.
- CRITICAL: You must ONLY read files that actually exist in the project. Check the "CURRENT DIRECTORY TREE STRUCTURE" list above to verify if a file exists before trying to read it. Do NOT guess, assume, or hallucinate file paths (e.g. project-overview.md, frontend-architecture.md, etc.) if they are not listed in the tree.
- CRITICAL: If a file's content is already provided in the ADDITIONAL CONTEXT, DO NOT use [READ_FILE] on it and DO NOT print its code in your response. Answer the user directly!
- After writing or editing a file, ALWAYS run [RUN_TESTS] or [LINT_CODE] to verify your changes don't break anything.
- If the user is only asking a question, explanation, or general query that does NOT require modifying files or running commands, answer the query directly and append [FINISH] at the end of your response. Do NOT call other tools like [READ_FILE] or [LIST_DIR] unnecessarily.
- CRITICAL RENAME / REFACOR RULE: When the user asks to rename something (a function, variable, class, method, file, folder, or any identifier), you MUST:
  1. First use [SEARCH_FILES: old_name] to find ALL files that reference or contain the old name.
  2. Then use [REGEX_SEARCH: old_name | *.py] (and similar for *.js, *.ts, etc.) to ensure you don't miss any references.
  3. Read each file that contains the old name using [READ_FILE].
  4. Update ALL occurrences across ALL files using [EDIT_FILE] on each file.
  5. Only after updating ALL files, output [FINISH].
  NEVER rename in just one file. The goal is to perform a project-wide rename.

EXAMPLE — Fixing a bug:
[SEARCH_FILES: def login]
[READ_FILE: src/auth.py]

After reading, apply fix:
[EDIT_FILE: src/auth.py]
<<<SEARCH>>>    if user.password == password:<<<END_SEARCH>>>
<<<REPLACE>>>    if user.check_password(password):<<<END_REPLACE>>>

Then verify:
[RUN_TESTS]

After tests pass:
[FINISH]

EXAMPLE — Creating a new file:
[LIST_DIR: src/utils]
[WRITE_FILE: src/utils/date.js]
```javascript
export function formatDate(date) {{
  return new Intl.DateTimeFormat('en-US').format(date);
}}
```

[RUN_TESTS]
[FINISH]
"""
        else:
            system_prompt = f"""You are a helpful software engineering assistant helping the user work on a local project workspace.
{lang_instruction}

CURRENT DIRECTORY TREE STRUCTURE:
```
{tree_str}
```
{context_str}

Answer the user's questions about the project files directly, explain code, or answer general queries.
Since you are in direct chat mode, do NOT use any tool call tags such as [READ_FILE], [WRITE_FILE], [LIST_DIR], [SEARCH_FILES], [RUN_COMMAND], or [FINISH].
Provide clear, well-structured explanations and code suggestions where appropriate.
For thought process, keep it extremely concise (1-2 sentences) inside <think>...</think>. For simple greetings or casual chat, SKIP the thought process and reply immediately.
"""

        messages = [{"role": "system", "content": system_prompt}]

        # Retrieve history
        history = retrieve_chat_history(session_id, config.PROJECT_HISTORY_LIMIT, skip_first=False)
        log.db_query("ChatMessage", session_id, count=len(history))
        messages.extend(history)

        # Save user message to history
        save_chat_message(session_id, 'user', question)
        log.info("User question saved", question_preview=question[:120])

        # Append current user question
        messages.append({"role": "user", "content": question})

        max_iterations = config.AGENT_MAX_ITERATIONS if agent_mode else 1
        initial_messages_count = len(messages)
        log.info("Context ready", total_messages=len(messages), max_iterations=max_iterations)

        for iteration in range(max_iterations):
            log.agent_iteration(session_id, iteration, max_iterations)

            # Send iteration status
            status_msg = f"AI is thinking (Loop {iteration+1}/10)..." if language == 'en' else f"AI đang suy nghĩ (Vòng lặp {iteration+1}/10)..."
            yield format_sse_event('agent_status', status=status_msg)
            time.sleep(0.1)

            # Call Ollama
            current_answer = ""
            log.agent_ollama_call(session_id, iteration, len(messages))
            ollama_start = time.time()
            generator = call_ollama(messages, model, stream=True)
            
            for chunk in generator:
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str != "[DONE]":
                        try:
                            data_json = json.loads(data_str)
                            if "content" in data_json:
                                content = data_json["content"]
                                current_answer += content
                                yield format_sse_event('content', content=content)
                            elif "error" in data_json:
                                error_msg = data_json["error"]
                                log.error("Ollama returned error in stream", error=error_msg)
                                yield format_sse_event('content', content=f"❌ **Error:** {error_msg}")
                        except:
                            pass

            ollama_ms = (time.time() - ollama_start) * 1000
            log.agent_ollama_response(session_id, iteration, len(current_answer))
            log.ollama_success(ollama_ms)

            # Append assistant response to messages history
            messages.append({"role": "assistant", "content": current_answer})

            # Parse tool calls
            tool_calls = parse_all_tool_calls(current_answer)
            tool_names = [tc['tool'] for tc in tool_calls]
            log.agent_parse_tools(session_id, iteration, len(tool_calls), tool_names)

            if not tool_calls:
                log.info("No tool calls → finishing loop")
                yield format_sse_event('agent_status', status='Finished (No tool call)' if language == 'en' else 'Hoàn thành (Không có tool call)')
                break

            # Check for FINISH (may appear alongside other tool calls)
            has_finish = any(tc['tool'] == 'FINISH' for tc in tool_calls)

            # Filter out FINISH so we execute all real tools first
            actionable_calls = [tc for tc in tool_calls if tc['tool'] != 'FINISH']

            if not actionable_calls:
                # Only FINISH (or empty) — nothing to execute
                log.success("FINISH detected → exiting agent loop")
                yield format_sse_event('agent_status', status='Agent finished tasks successfully!' if language == 'en' else 'Agent hoàn thành công việc thành công!')
                break
            
            results_contents = []
            for idx, tool_call in enumerate(actionable_calls):
                tool_name = tool_call['tool']
                tool_args = tool_call['args']
                call_id = f"call_{iteration}_{idx}"

                # Log and yield tool call event
                log.tool_call(tool_name, tool_args, call_id=call_id)
                yield format_sse_event('tool_call', tool=tool_name, args=tool_args, call_id=call_id)

                tool_status = f"Running tool {tool_name}..." if language == 'en' else f"Đang chạy tool {tool_name}..."
                if tool_name == 'READ_FILE':
                    tool_status = f"Reading file: {tool_args.get('path')}..." if language == 'en' else f"Đang đọc file: {tool_args.get('path')}..."
                elif tool_name == 'WRITE_FILE':
                    tool_status = f"Writing file: {tool_args.get('path')}..." if language == 'en' else f"Đang ghi file: {tool_args.get('path')}..."
                elif tool_name == 'RUN_COMMAND':
                    tool_status = f"Running command: {tool_args.get('command')}..." if language == 'en' else f"Đang chạy lệnh: {tool_args.get('command')}..."
                yield format_sse_event('agent_status', status=tool_status)
                time.sleep(0.05)

                # Execute tool with timing
                tool_start = time.time()
                tool_result = execute_agent_tool(tool_name, tool_args, project_path)
                tool_ms = (time.time() - tool_start) * 1000

                log.tool_result(tool_name, tool_result, call_id=call_id, duration_ms=tool_ms)

                if tool_name == 'WRITE_FILE':
                    invalidate_project_tree_cache(session_id)
                    log.info("Project tree cache invalidated (file was written)")

                # Yield tool result event
                display_result = tool_result
                if len(display_result) > 5000:
                    display_result = display_result[:5000] + "\n...[output truncated due to length]"
                yield format_sse_event('tool_result', tool=tool_name, args=tool_args, result=display_result, call_id=call_id)

                post_status = f"Finished tool {tool_name}." if language == 'en' else f"Đã chạy xong tool {tool_name}."
                yield format_sse_event('agent_status', status=post_status)
                time.sleep(0.05)

                # Format output for model prompt
                model_tool_result = tool_result
                if len(model_tool_result) > 15000:
                    model_tool_result = model_tool_result[:15000] + "\n\n...[content truncated to save context]..."
                results_contents.append(f"Tool execution result for [{tool_name}] with args {json.dumps(tool_args)}:\n{model_tool_result}")
            
            # Combine all results into one user message for the next iteration
            combined_results = "\n\n---\n\n".join(results_contents)
            log.info("Combining tool results for next iteration", tools_count=len(actionable_calls), results_size=len(combined_results))
            messages.append({
                "role": "user",
                "content": f"Tool execution results:\n\n{combined_results}\n\nPlease proceed to the next step."
            })

            # If FINISH was present alongside other tools, exit after executing them
            if has_finish:
                log.success("FINISH detected → exiting agent loop (after executing tools)")
                yield format_sse_event('agent_status', status='Agent finished tasks successfully!' if language == 'en' else 'Agent hoàn thành công việc thành công!')
                break

        # Save final response summary to SQLite
        final_summary = ""
        for msg in messages[initial_messages_count:]:
            if msg["role"] == "assistant":
                final_summary += msg["content"] + "\n\n"

        save_chat_message(session_id, 'assistant', final_summary.strip())
        log.agent_finish(session_id, max_iterations)
        log.info("Final response saved to DB", summary_length=len(final_summary.strip()))

        yield "data: [DONE]\n\n"
