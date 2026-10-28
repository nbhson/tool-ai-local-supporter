"""
╔══════════════════════════════════════════════════════════════╗
║  AI Local Support — Structured Logger                       ║
║  Beautiful, colored, easy-to-read log formatting            ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    from services.logger import log

    log.info("Agent started", session="abc123")
    log.tool_call("READ_FILE", path="main.py")
    log.ollama_request("mistral", messages_count=5)
"""

import json
import logging
import os
from datetime import datetime


# ── ANSI Color Codes ──────────────────────────────────────────
class C:
    """ANSI color codes for terminal output."""
    RESET      = "\033[0m"
    BOLD       = "\033[1m"
    DIM        = "\033[2m"
    UNDERLINE  = "\033[4m"
    # Foreground
    RED        = "\033[31m"
    GREEN      = "\033[32m"
    YELLOW     = "\033[33m"
    BLUE       = "\033[34m"
    MAGENTA    = "\033[35m"
    CYAN       = "\033[36m"
    WHITE      = "\033[37m"
    GRAY       = "\033[90m"
    BLACK      = "\033[30m"
    # Bright
    BRIGHT_RED     = "\033[91m"
    BRIGHT_GREEN   = "\033[92m"
    BRIGHT_YELLOW  = "\033[93m"
    BRIGHT_BLUE    = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_WHITE   = "\033[97m"
    BRIGHT_CYAN    = "\033[96m"
    # Backgrounds
    BG_RED     = "\033[41m"
    BG_GREEN   = "\033[42m"
    BG_YELLOW  = "\033[43m"
    BG_BLUE    = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN    = "\033[46m"


# ── Disable colors if not a TTY or NO_COLOR is set ────────────
_NO_COLOR = os.environ.get("NO_COLOR", "").strip() != "" or not os.isatty(2)

if _NO_COLOR:
    class _NoColor:
        """Strip all ANSI codes."""
        def __getattr__(self, _): return ""
    C = _NoColor()  # type: ignore


# ── Helper functions ──────────────────────────────────────────

def _ts():
    """Compact timestamp: HH:MM:SS.mmm"""
    now = datetime.now()
    return now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"

def _truncate(s, maxlen=200):
    """Truncate a string to maxlen characters."""
    if not s:
        return s
    s = str(s)
    if len(s) <= maxlen:
        return s
    return s[:maxlen] + f"... ({len(s)} chars total)"

def _short_session(session_id):
    """Show only first 8 chars of session_id."""
    if not session_id:
        return "????????"
    return session_id[:8]


# ── Log tag styles ────────────────────────────────────────────
# Each tag has: (label, fg_color, bg_color)
_TAGS = {
    "info":        (" INFO ", C.WHITE,      ""),
    "debug":       (" DEBUG", C.GRAY,       ""),
    "warning":     (" WARN ", C.BLACK,      C.BG_YELLOW),
    "error":       (" ERROR", C.WHITE,      C.BG_RED),
    "success":     ("  OK  ", C.WHITE,      C.BG_GREEN),
    # Domain-specific tags
    "agent":       (" AGENT", C.BRIGHT_CYAN,    ""),
    "ollama":      ("OLLAMA", C.BRIGHT_MAGENTA, ""),
    "tool":        (" TOOL ", C.BRIGHT_YELLOW,   ""),
    "sse":         (" SSE  ", C.BRIGHT_BLUE,     ""),
    "session":     ("SESSION", C.BRIGHT_GREEN,   ""),
    "db":          ("  DB  ", C.CYAN,        ""),
    "route":       ("ROUTE ", C.BLUE,        ""),
    "parse":       ("PARSE ", C.YELLOW,      ""),
}


def _format_tag(tag_name):
    """Render a colored tag block like [ AGENT]."""
    label, fg, bg = _TAGS.get(tag_name, _TAGS["info"])
    if bg:
        return f"{C.BOLD}{bg}{C.WHITE} {label} {C.RESET}{fg}"
    return f"{C.BOLD}{fg}[{label}]{C.RESET} {fg}"


def _format_header(title, width=60):
    """Render a decorative section header."""
    line = "═" * width
    return (
        f"\n"
        f"{C.CYAN}{C.BOLD}╔{line}╗{C.RESET}\n"
        f"{C.CYAN}{C.BOLD}║{C.RESET} {C.BOLD}{title}{C.RESET}{' ' * max(0, width - len(title) - 2)}{C.CYAN}{C.BOLD}║{C.RESET}\n"
        f"{C.CYAN}{C.BOLD}╚{line}╝{C.RESET}"
    )


# ── Main Logger Class ─────────────────────────────────────────

class AILogger:
    """
    Structured logger for AI Local Support.

    Provides domain-specific methods with beautiful formatting.
    Falls back to standard logging for non-TTY environments.
    """

    def __init__(self, name="ai-support"):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(message)s",
            ))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)

    def _log(self, tag, message, **kwargs):
        """Core log method with tag and optional key=value pairs."""
        ts = _ts()
        tag_str = _format_tag(tag)
        extra = ""
        if kwargs:
            pairs = " │ ".join(f"{C.DIM}{k}{C.RESET}={C.BRIGHT_WHITE}{_truncate(v, 80)}{C.RESET}" for k, v in kwargs.items())
            extra = f"\n{C.GRAY}{'':>20}└─ {pairs}{C.RESET}"

        line = f"{C.GRAY}{ts}{C.RESET} {tag_str}{message}{extra}"
        self.logger.info(line)

    # ── Basic Levels ──────────────────────────────────────────

    def info(self, message, **kwargs):
        self._log("info", message, **kwargs)

    def debug(self, message, **kwargs):
        self._log("debug", message, **kwargs)

    def warning(self, message, **kwargs):
        self._log("warning", f"{C.YELLOW}{message}{C.RESET}", **kwargs)

    def error(self, message, **kwargs):
        self._log("error", f"{C.RED}{message}{C.RESET}", **kwargs)

    def success(self, message, **kwargs):
        self._log("success", f"{C.GREEN}{message}{C.RESET}", **kwargs)

    # ── Decorative Headers ────────────────────────────────────

    def header(self, title, width=60):
        """Log a decorative section header."""
        self.logger.info(_format_header(title, width))

    def separator(self):
        """Log a thin separator line."""
        self.logger.info(f"{C.GRAY}{'─' * 70}{C.RESET}")

    # ── Domain: Agent Loop ────────────────────────────────────

    def agent_start(self, session_id, question, model, agent_mode):
        """Log agent session start."""
        self.header(f"🤖 AGENT SESSION START — {_short_session(session_id)}")
        self._log("agent", f"{C.GREEN}Agent loop initialized{C.RESET}", session=_short_session(session_id), model=model, mode="agent" if agent_mode else "chat")

    def agent_iteration(self, session_id, iteration, max_iter):
        """Log start of an agent iteration."""
        self.separator()
        self._log("agent", f"{C.BOLD}🔄 Iteration {C.BRIGHT_CYAN}{iteration + 1}{C.RESET}{C.BOLD}/{max_iter}{C.RESET}", session=_short_session(session_id))

    def agent_ollama_call(self, session_id, iteration, messages_count):
        """Log when Ollama API is called."""
        self._log("ollama", "📞 Calling Ollama API...", session=_short_session(session_id), iteration=iteration + 1, messages_in_context=messages_count)

    def agent_ollama_response(self, session_id, iteration, response_len):
        """Log when Ollama response is received."""
        self._log("ollama", f"📥 Response received: {C.BRIGHT_WHITE}{response_len}{C.RESET} chars", session=_short_session(session_id), iteration=iteration + 1)

    def agent_parse_tools(self, session_id, iteration, tool_count, tool_names):
        """Log parsed tool calls."""
        if tool_count == 0:
            self._log("parse", f"{C.DIM}No tool calls found in response{C.RESET}", session=_short_session(session_id))
        else:
            names = ", ".join(tool_names)
            self._log("parse", f"🔧 Found {C.BRIGHT_WHITE}{tool_count}{C.RESET} tool call(s): {C.BRIGHT_YELLOW}{names}{C.RESET}", session=_short_session(session_id))

    def agent_finish(self, session_id, total_iterations):
        """Log agent loop completion."""
        self._log("agent", f"{C.GREEN}{C.BOLD}✅ Agent finished after {total_iterations} iteration(s){C.RESET}", session=_short_session(session_id))
        self.separator()

    # ── Domain: Tool Execution ────────────────────────────────

    def tool_call(self, tool_name, args, call_id=""):
        """Log when a tool is about to be executed."""
        arg_summary = self._summarize_tool_args(tool_name, args)
        self._log("tool", f"{C.BOLD}▶ {C.BRIGHT_YELLOW}{tool_name}{C.RESET} {C.DIM}{arg_summary}{C.RESET}", call_id=call_id)

    def tool_result(self, tool_name, result, call_id="", duration_ms=None):
        """Log tool execution result."""
        status = "success" if not result.startswith("Error") else "error"
        icon = "✅" if status == "success" else "❌"
        dur = f"{duration_ms:.0f}ms" if duration_ms else ""
        preview = _truncate(result.replace("\n", " "), 120)
        self._log("tool", f"{icon} {C.BOLD}◀ {tool_name}{C.RESET} {preview}", call_id=call_id, duration=dur)

    # ── Domain: Ollama API ────────────────────────────────────

    def ollama_request(self, model, messages_count, stream=True):
        """Log Ollama API request."""
        self._log("ollama", f"📤 POST {C.UNDERLINE}{model}{C.RESET} │ messages={messages_count} │ stream={stream}")

    def ollama_retry(self, attempt, max_retries, reason):
        """Log Ollama retry."""
        self._log("warning", f"🔁 Retry {attempt + 1}/{max_retries}: {C.YELLOW}{reason}{C.RESET}")

    def ollama_error(self, status_code, detail):
        """Log Ollama error."""
        self._log("error", f"Ollama API error {C.BRIGHT_RED}{status_code}{C.RESET}: {_truncate(detail, 150)}")

    def ollama_success(self, duration_ms):
        """Log Ollama success."""
        self._log("success", f"Ollama call completed in {C.BRIGHT_GREEN}{duration_ms:.0f}ms{C.RESET}")

    # ── Domain: SSE Events ────────────────────────────────────

    def sse_send(self, event_type, session_id="", **extra):
        """Log an SSE event being sent to client."""
        extra_str = " │ ".join(f"{k}={_truncate(v, 60)}" for k, v in extra.items())
        self._log("sse", f"→ {C.BRIGHT_CYAN}{event_type}{C.RESET} {C.DIM}{extra_str}{C.RESET}", session=_short_session(session_id))

    # ── Domain: Routes ────────────────────────────────────────

    def route_request(self, method, endpoint, **kwargs):
        """Log incoming HTTP request."""
        pairs = " │ ".join(f"{k}={_truncate(v, 60)}" for k, v in kwargs.items())
        self._log("route", f"{C.BOLD}→ {method} {C.UNDERLINE}{endpoint}{C.RESET} {C.DIM}{pairs}{C.RESET}")

    def route_response(self, endpoint, status_code):
        """Log HTTP response."""
        color = C.GREEN if 200 <= status_code < 400 else C.RED
        self._log("route", f"{color}← {status_code}{C.RESET}")

    # ── Domain: Session ───────────────────────────────────────

    def session_init(self, session_id, kind="project"):
        """Log session initialization."""
        self._log("session", f"🆕 {kind.capitalize()} session created: {C.BRIGHT_GREEN}{session_id[:12]}...{C.RESET}")

    def session_chat_start(self, session_id, question, agent_mode):
        """Log the start of a chat interaction in a session."""
        self.header(f"💬 CHAT — Session {_short_session(session_id)}")
        self._log("session", f"Question: {C.BRIGHT_WHITE}{_truncate(question, 150)}{C.RESET}", session=_short_session(session_id), agent_mode=agent_mode)

    # ── Domain: DB ────────────────────────────────────────────

    def db_save(self, table, session_id, extra=""):
        """Log a database save operation."""
        self._log("db", f"💾 INSERT {table} │ session={_short_session(session_id)} {extra}")

    def db_query(self, table, session_id, count=None):
        """Log a database query."""
        count_str = f" → {count} rows" if count is not None else ""
        self._log("db", f"🔍 SELECT {table} │ session={_short_session(session_id)}{count_str}")

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _summarize_tool_args(tool_name, args):
        """Create a compact summary of tool arguments."""
        if tool_name == "READ_FILE":
            return f"({args.get('path', '?')})"
        elif tool_name == "WRITE_FILE":
            content = args.get('content', '')
            return f"({args.get('path', '?')}, {len(content)} chars)"
        elif tool_name == "EDIT_FILE":
            search = args.get('search', '')
            return f"({args.get('path', '?')}, search={len(search)} chars)"
        elif tool_name == "LIST_DIR":
            return f"({args.get('path', '.')})"
        elif tool_name == "SEARCH_FILES":
            return f"(query='{args.get('query', '')}')"
        elif tool_name == "REGEX_SEARCH":
            return f"(pattern='{args.get('pattern', '')}')"
        elif tool_name == "RUN_COMMAND":
            return f"({args.get('command', '')})"
        elif tool_name == "RUN_TESTS" or tool_name == "LINT_CODE":
            cmd = args.get('command', '')
            return f"({cmd})" if cmd else "(auto-detect)"
        elif tool_name == "GIT_DIFF":
            p = args.get('path', '')
            return f"({p})" if p else "(all)"
        elif tool_name == "GIT_LOG":
            return f"(count={args.get('count', '10')})"
        elif tool_name == "FINISH":
            return ""
        else:
            return f"({json.dumps(args)[:80]})"


# ── Global singleton ──────────────────────────────────────────
log = AILogger()