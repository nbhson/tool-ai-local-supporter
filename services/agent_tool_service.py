import os
import re
import subprocess
import shlex
import config
from services.helper_service import safe_join_project_path
from services.logger import log


# Whitelist of allowed commands (prefix match). Commands not starting with
# any allowed prefix are rejected. This is a safety guard for the shell=True
# execution path — do NOT add generic entries like "sh" or "bash" here.
ALLOWED_CMD_PREFIXES = (
    "python", "python3", "pip", "pip3",
    "npm", "npx", "node", "bun", "pnpm",
    "cargo", "rustc", "go", "make",
    "git", "ruff", "flake8", "eslint",
    "curl", "wget",
)


def _is_cmd_allowed(command: str) -> bool:
    """Check if command starts with an allowed prefix (simple safety gate)."""
    first_word = command.strip().split()[0] if command.strip() else ""
    return any(first_word.startswith(p) for p in ALLOWED_CMD_PREFIXES)


class BaseAgentTool:
    def execute(self, args: dict, project_path: str) -> str:
        raise NotImplementedError("Each tool must implement execute")

class ReadFileTool(BaseAgentTool):
    def execute(self, args: dict, project_path: str) -> str:
        path = args.get('path', '').strip()
        try:
            filepath = safe_join_project_path(project_path, path)
        except ValueError as e:
            return f"Error: {str(e)}"
        if not os.path.exists(filepath):
            return f"Error: File not found: {path}"
        if os.path.isdir(filepath):
            return f"Error: {path} is a directory. Use LIST_DIR instead."
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return f"--- Content of {path} ---\n{content}\n----------------"
        except Exception as e:
            return f"Error reading file: {str(e)}"

class WriteFileTool(BaseAgentTool):
    def execute(self, args: dict, project_path: str) -> str:
        path = args.get('path', '').strip()
        content = args.get('content', '')
        try:
            filepath = safe_join_project_path(project_path, path)
        except ValueError as e:
            return f"Error: {str(e)}"
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Success: File written successfully to {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

class ListDirTool(BaseAgentTool):
    def execute(self, args: dict, project_path: str) -> str:
        path = args.get('path', '').strip()
        try:
            target_path = safe_join_project_path(project_path, path)
        except ValueError as e:
            return f"Error: {str(e)}"
        if not os.path.exists(target_path):
            return f"Error: Directory not found: {path}"
        try:
            entries = []
            for entry in os.scandir(target_path):
                if entry.name in config.EXCLUDE_DIRS or entry.name in config.EXCLUDE_FILES:
                    continue
                rel = os.path.relpath(entry.path, project_path)
                entries.append(f"{'[DIR]' if entry.is_dir() else '[FILE]'} {rel}")
            return "\n".join(sorted(entries)) if entries else "Empty directory"
        except Exception as e:
            return f"Error listing directory: {str(e)}"

class SearchFilesTool(BaseAgentTool):
    def execute(self, args: dict, project_path: str) -> str:
        query = args.get('query', '').strip()
        if not query:
            return "Error: Empty search query"
        results = []
        query_lower = query.lower()
        try:
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in config.EXCLUDE_DIRS]
                for f in files:
                    if f in config.EXCLUDE_FILES:
                        continue
                    rel_path = os.path.relpath(os.path.join(root, f), project_path)
                    if query_lower in rel_path.lower():
                        results.append(f"Match in filename: {rel_path}")
                    filepath = os.path.join(root, f)
                    if os.path.getsize(filepath) > 500000: # Skip files larger than 500KB
                        continue
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as file_obj:
                            content = file_obj.read()
                            if query_lower in content.lower():
                                lines = content.split('\n')
                                for idx, line in enumerate(lines):
                                    if query_lower in line.lower():
                                        results.append(f"{rel_path}:{idx+1}: {line.strip()[:120]}")
                    except:
                        pass
            return "\n".join(results[:50]) if results else "No matches found"
        except Exception as e:
            return f"Error searching files: {str(e)}"

class RunCommandTool(BaseAgentTool):
    def execute(self, args: dict, project_path: str) -> str:
        command = args.get('command', '').strip()
        if not command:
            return "Error: Empty command"
        if not _is_cmd_allowed(command):
            return (f"Error: Command '{command.split()[0]}' is not in the allowed list. "
                    f"Allowed prefixes: {', '.join(ALLOWED_CMD_PREFIXES)}")
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            output = f"Exit code: {res.returncode}\n"
            if res.stdout:
                output += f"STDOUT:\n{res.stdout}\n"
            if res.stderr:
                output += f"STDERR:\n{res.stderr}\n"
            return output
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 30 seconds."
        except Exception as e:
            return f"Error executing command: {str(e)}"

class FinishTool(BaseAgentTool):
    def execute(self, args: dict, project_path: str) -> str:
        return "Agent finished tasks successfully!"

class EditFileTool(BaseAgentTool):
    """Replace a specific string in a file with new content (targeted edit)."""
    def execute(self, args: dict, project_path: str) -> str:
        path = args.get('path', '').strip()
        search = args.get('search', '')
        replace = args.get('replace', '')
        if not path:
            return "Error: Empty file path"
        if not search:
            return "Error: Empty search string"
        try:
            filepath = safe_join_project_path(project_path, path)
        except ValueError as e:
            return f"Error: {str(e)}"
        if not os.path.exists(filepath):
            return f"Error: File not found: {path}"
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            if search not in content:
                return f"Error: Search string not found in {path}. The content may have changed — try reading the file first."
            count = content.count(search)
            if count > 1:
                return f"Error: Search string found {count} times in {path}. Provide a more unique search string (include surrounding lines)."
            new_content = content.replace(search, replace, 1)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return f"Success: File edited successfully at {path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"


class GitDiffTool(BaseAgentTool):
    """Show git diff (unstaged changes) in the project."""
    def execute(self, args: dict, project_path: str) -> str:
        file_path = args.get('path', '').strip()
        try:
            cmd = ['git', 'diff']
            if file_path:
                cmd.append('--')
                cmd.append(file_path)
            res = subprocess.run(cmd, cwd=project_path, capture_output=True, text=True, timeout=15)
            output = res.stdout.strip()
            if not output:
                return "No unstaged changes found."
            # Truncate if too long
            if len(output) > 20000:
                output = output[:20000] + "\n...[diff truncated]"
            return output
        except FileNotFoundError:
            return "Error: git is not installed or not in PATH."
        except Exception as e:
            return f"Error running git diff: {str(e)}"


class GitLogTool(BaseAgentTool):
    """Show recent git commit log."""
    def execute(self, args: dict, project_path: str) -> str:
        count = args.get('count', '10').strip()
        try:
            n = int(count) if count.isdigit() else 10
            n = min(n, 50)
            res = subprocess.run(
                ['git', 'log', f'-{n}', '--oneline', '--no-decorate'],
                cwd=project_path, capture_output=True, text=True, timeout=15
            )
            output = res.stdout.strip()
            return output if output else "No commits found."
        except FileNotFoundError:
            return "Error: git is not installed or not in PATH."
        except Exception as e:
            return f"Error running git log: {str(e)}"


class RunTestsTool(BaseAgentTool):
    """Auto-detect and run the project's test suite."""
    def execute(self, args: dict, project_path: str) -> str:
        command = args.get('command', '').strip()
        if command:
            # User specified a custom test command
            return self._run_cmd(command, project_path)

        # Auto-detect test framework
        detectors = [
            ('pytest.ini', 'pyproject.toml', 'setup.cfg', 'conftest.py'),
            ('package.json',),
            ('Makefile',),
            ('Cargo.toml',),
            ('go.mod',),
        ]
        py_files = [f for f in os.listdir(project_path) if f.startswith('test_') and f.endswith('.py')]
        js_test_dirs = os.path.exists(os.path.join(project_path, 'jest.config.js')) or \
                       os.path.exists(os.path.join(project_path, 'vitest.config.js'))

        # Python: pytest
        if any(os.path.exists(os.path.join(project_path, d)) for d in detectors[0]) or py_files:
            return self._run_cmd('python -m pytest --tb=short -q', project_path)

        # Node.js
        if os.path.exists(os.path.join(project_path, 'package.json')):
            pkg_path = os.path.join(project_path, 'package.json')
            try:
                import json as _json
                with open(pkg_path, 'r') as f:
                    pkg = _json.load(f)
                scripts = pkg.get('scripts', {})
                test_cmd = 'npm test' if 'test' in scripts else None
                if test_cmd:
                    return self._run_cmd(test_cmd, project_path)
            except Exception:
                pass
            if js_test_dirs:
                return self._run_cmd('npx jest --passWithNoTests', project_path)

        # Rust
        if os.path.exists(os.path.join(project_path, 'Cargo.toml')):
            return self._run_cmd('cargo test --quiet', project_path)

        # Go
        if os.path.exists(os.path.join(project_path, 'go.mod')):
            return self._run_cmd('go test ./...', project_path)

        # Makefile
        if os.path.exists(os.path.join(project_path, 'Makefile')):
            try:
                with open(os.path.join(project_path, 'Makefile'), 'r') as f:
                    content = f.read()
                if 'test:' in content:
                    return self._run_cmd('make test', project_path)
            except Exception:
                pass

        return "Error: Could not auto-detect test framework. Please specify a custom test command with [RUN_TESTS: your-command]."

    @staticmethod
    def _run_cmd(command, project_path):
        if not _is_cmd_allowed(command):
            return (f"Error: Command '{command.split()[0] if command.split() else ''}' is not in the allowed list. "
                    f"Allowed prefixes: {', '.join(ALLOWED_CMD_PREFIXES)}")
        try:
            res = subprocess.run(
                command, shell=True, cwd=project_path,
                capture_output=True, text=True, timeout=60
            )
            output = f"Exit code: {res.returncode}\n"
            if res.stdout:
                output += f"STDOUT:\n{res.stdout}\n"
            if res.stderr:
                output += f"STDERR:\n{res.stderr}\n"
            if len(output) > 15000:
                output = output[:15000] + "\n...[output truncated]"
            return output
        except subprocess.TimeoutExpired:
            return "Error: Tests timed out after 60 seconds."
        except Exception as e:
            return f"Error running tests: {str(e)}"


class LintCodeTool(BaseAgentTool):
    """Auto-detect and run linter on the project."""
    def execute(self, args: dict, project_path: str) -> str:
        command = args.get('command', '').strip()
        if command:
            return self._run_lint_cmd(command, project_path)

        # Auto-detect linter
        if os.path.exists(os.path.join(project_path, '.eslintrc.js')) or \
           os.path.exists(os.path.join(project_path, '.eslintrc.json')) or \
           os.path.exists(os.path.join(project_path, 'eslint.config.js')):
            return self._run_lint_cmd('npx eslint --max-warnings 50 .', project_path)

        if os.path.exists(os.path.join(project_path, '.flake8')) or \
           os.path.exists(os.path.join(project_path, 'setup.cfg')) or \
           os.path.exists(os.path.join(project_path, 'pyproject.toml')):
            return self._run_lint_cmd('python -m flake8 --max-line-length=120 --count', project_path)

        # Ruff (fast Python linter)
        py_files = [f for f in os.listdir(project_path) if f.endswith('.py')]
        if py_files:
            return self._run_lint_cmd('python -m ruff check --output-format=text', project_path)

        return "Error: Could not auto-detect linter. Please specify a custom lint command with [LINT_CODE: your-command]."

    @staticmethod
    def _run_lint_cmd(command, project_path):
        if not _is_cmd_allowed(command):
            return (f"Error: Command '{command.split()[0] if command.split() else ''}' is not in the allowed list. "
                    f"Allowed prefixes: {', '.join(ALLOWED_CMD_PREFIXES)}")
        try:
            res = subprocess.run(
                command, shell=True, cwd=project_path,
                capture_output=True, text=True, timeout=60
            )
            output = ""
            if res.stdout:
                output += res.stdout
            if res.stderr:
                output += f"\nSTDERR:\n{res.stderr}"
            output = f"Exit code: {res.returncode}\n{output.strip()}"
            if len(output) > 15000:
                output = output[:15000] + "\n...[output truncated]"
            return output
        except subprocess.TimeoutExpired:
            return "Error: Linting timed out after 60 seconds."
        except Exception as e:
            return f"Error running linter: {str(e)}"


class RegexSearchTool(BaseAgentTool):
    """Search files using regex patterns."""
    def execute(self, args: dict, project_path: str) -> str:
        pattern = args.get('pattern', '').strip()
        file_pattern = args.get('file_pattern', '').strip()
        if not pattern:
            return "Error: Empty regex pattern"
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Error: Invalid regex pattern: {str(e)}"

        results = []
        try:
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in config.EXCLUDE_DIRS]
                for f in files:
                    if f in config.EXCLUDE_FILES:
                        continue
                    if file_pattern and not re.search(file_pattern, f):
                        continue
                    filepath = os.path.join(root, f)
                    rel_path = os.path.relpath(filepath, project_path)
                    if os.path.getsize(filepath) > 500000:
                        continue
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as fh:
                            for idx, line in enumerate(fh, 1):
                                if compiled.search(line):
                                    results.append(f"{rel_path}:{idx}: {line.strip()[:120]}")
                    except Exception:
                        pass
                    if len(results) >= 50:
                        break
                if len(results) >= 50:
                    break
            return "\n".join(results) if results else "No matches found."
        except Exception as e:
            return f"Error searching files: {str(e)}"


class ToolRegistry:
    _tools = {
        'READ_FILE': ReadFileTool(),
        'WRITE_FILE': WriteFileTool(),
        'EDIT_FILE': EditFileTool(),
        'LIST_DIR': ListDirTool(),
        'SEARCH_FILES': SearchFilesTool(),
        'REGEX_SEARCH': RegexSearchTool(),
        'RUN_COMMAND': RunCommandTool(),
        'RUN_TESTS': RunTestsTool(),
        'LINT_CODE': LintCodeTool(),
        'GIT_DIFF': GitDiffTool(),
        'GIT_LOG': GitLogTool(),
        'FINISH': FinishTool()
    }

    @classmethod
    def execute_tool(cls, tool_name: str, args: dict, project_path: str) -> str:
        tool = cls._tools.get(tool_name)
        if not tool:
            log.error(f"Unknown tool requested: {tool_name}")
            return f"Error: Unknown tool {tool_name}"
        log.debug(f"ToolRegistry dispatch → {tool_name}")
        return tool.execute(args, project_path)
