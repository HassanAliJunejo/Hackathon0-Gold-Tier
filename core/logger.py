"""
Universal Audit Logger - Gold Tier Autonomous Employee
Centralized logging system for all MCP servers and skills.

Features:
- Structured logging with timestamps
- Action type categorization
- Status tracking (SUCCESS, FAILED, PENDING, etc.)
- Error capture with stack traces
- Source skill/service attribution
- Multiple output formats (Markdown, JSON, Console)
- Log rotation and archiving
"""

import os
import json
import sys
import traceback
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field, asdict
from functools import wraps
import threading
import asyncio

# =============================================================================
# Configuration
# =============================================================================

BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "Logs"

# Log files
MASTER_LOG = LOGS_DIR / "master_audit.md"
JSON_LOG = LOGS_DIR / "audit.json"
ERROR_LOG = LOGS_DIR / "errors.md"

# Rotation settings
MAX_LOG_SIZE_MB = 10
MAX_LOG_AGE_DAYS = 30


# =============================================================================
# Enums
# =============================================================================

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    SUCCESS = "SUCCESS"


class ActionType(str, Enum):
    # System actions
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    HEALTH_CHECK = "health_check"

    # Task actions
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRY = "task_retry"

    # Approval workflow
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"

    # External API calls
    API_REQUEST = "api_request"
    API_RESPONSE = "api_response"
    API_ERROR = "api_error"

    # Data operations
    DATA_READ = "data_read"
    DATA_WRITE = "data_write"
    DATA_DELETE = "data_delete"

    # Report generation
    REPORT_GENERATED = "report_generated"

    # Generic
    CUSTOM = "custom"


class ServiceSource(str, Enum):
    RALPH_LOOP = "ralph_loop"
    ODOO_SERVER = "odoo_server"
    SOCIAL_MEDIA = "social_media"
    X_PUBLISHER = "x_publisher"
    CEO_BRIEFING = "ceo_briefing"
    ERROR_HANDLER = "error_handler"
    SYSTEM = "system"
    UNKNOWN = "unknown"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: str
    level: LogLevel
    action_type: ActionType
    status: str
    source: ServiceSource
    message: str
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    stack_trace: Optional[str] = None
    duration_ms: Optional[float] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """Convert to Markdown format."""
        icon = {
            LogLevel.DEBUG: "🔍",
            LogLevel.INFO: "ℹ️",
            LogLevel.WARNING: "⚠️",
            LogLevel.ERROR: "❌",
            LogLevel.CRITICAL: "🚨",
            LogLevel.SUCCESS: "✅"
        }.get(self.level, "📝")

        md = f"""
---

## {icon} [{self.level.value}] {self.action_type.value}

| Field | Value |
|-------|-------|
| **Timestamp** | {self.timestamp} |
| **Source** | {self.source.value} |
| **Status** | {self.status} |
| **Message** | {self.message} |
"""
        if self.duration_ms:
            md += f"| **Duration** | {self.duration_ms:.2f}ms |\n"

        if self.request_id:
            md += f"| **Request ID** | {self.request_id} |\n"

        if self.details:
            md += f"\n### Details\n\n```json\n{json.dumps(self.details, indent=2)}\n```\n"

        if self.error:
            md += f"\n### Error\n\n```\n{self.error}\n```\n"

        if self.stack_trace:
            md += f"\n### Stack Trace\n\n```\n{self.stack_trace}\n```\n"

        return md


# =============================================================================
# Logger Implementation
# =============================================================================

class AuditLogger:
    """
    Universal audit logger for Gold Tier Autonomous Employee.

    Usage:
        logger = AuditLogger(source=ServiceSource.ODOO_SERVER)
        logger.info("Invoice created", action=ActionType.DATA_WRITE, details={"id": 123})
        logger.error("API call failed", action=ActionType.API_ERROR, error=e)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern for global logger access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        source: ServiceSource = ServiceSource.UNKNOWN,
        console_output: bool = True,
        file_output: bool = True,
        json_output: bool = True
    ):
        if self._initialized:
            # Allow source override for different services
            self.source = source
            return

        self.source = source
        self.console_output = console_output
        self.file_output = file_output
        self.json_output = json_output

        # Ensure log directory exists
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        # Initialize log files
        self._init_log_files()

        self._initialized = True

    def _init_log_files(self):
        """Initialize log files with headers."""
        if not MASTER_LOG.exists():
            header = f"""# Master Audit Log

**Gold Tier Autonomous Employee**
**Created:** {datetime.now().isoformat()}

All system actions are logged here for audit compliance.

"""
            with open(MASTER_LOG, "w", encoding="utf-8") as f:
                f.write(header)

        if not ERROR_LOG.exists():
            header = f"""# Error Log

**Gold Tier Autonomous Employee**
**Created:** {datetime.now().isoformat()}

All errors and exceptions are logged here.

"""
            with open(ERROR_LOG, "w", encoding="utf-8") as f:
                f.write(header)

        if not JSON_LOG.exists():
            with open(JSON_LOG, "w", encoding="utf-8") as f:
                f.write("[]")

    def _check_rotation(self):
        """Check if log files need rotation."""
        for log_file in [MASTER_LOG, ERROR_LOG]:
            if log_file.exists():
                size_mb = log_file.stat().st_size / (1024 * 1024)
                if size_mb >= MAX_LOG_SIZE_MB:
                    self._rotate_log(log_file)

    def _rotate_log(self, log_file: Path):
        """Rotate a log file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{log_file.stem}_{timestamp}{log_file.suffix}"
        archive_path = LOGS_DIR / "archive" / archive_name

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        log_file.rename(archive_path)

    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        import uuid
        return str(uuid.uuid4())[:8]

    def _create_entry(
        self,
        level: LogLevel,
        message: str,
        action: ActionType = ActionType.CUSTOM,
        status: str = "OK",
        details: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
        duration_ms: Optional[float] = None,
        request_id: Optional[str] = None
    ) -> LogEntry:
        """Create a structured log entry."""
        error_str = None
        stack_trace = None

        if error:
            error_str = f"{type(error).__name__}: {str(error)}"
            stack_trace = traceback.format_exc()
            if status == "OK":
                status = "FAILED"

        return LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            action_type=action,
            status=status,
            source=self.source,
            message=message,
            details=details,
            error=error_str,
            stack_trace=stack_trace,
            duration_ms=duration_ms,
            request_id=request_id or self._generate_request_id()
        )

    def _write_entry(self, entry: LogEntry):
        """Write entry to all configured outputs."""
        self._check_rotation()

        # Console output
        if self.console_output:
            self._write_console(entry)

        # Markdown file output
        if self.file_output:
            self._write_markdown(entry)

        # JSON file output
        if self.json_output:
            self._write_json(entry)

        # Write errors to dedicated error log
        if entry.level in (LogLevel.ERROR, LogLevel.CRITICAL):
            self._write_error_log(entry)

    def _write_console(self, entry: LogEntry):
        """Write to console with colors."""
        colors = {
            LogLevel.DEBUG: "\033[90m",      # Gray
            LogLevel.INFO: "\033[94m",       # Blue
            LogLevel.WARNING: "\033[93m",    # Yellow
            LogLevel.ERROR: "\033[91m",      # Red
            LogLevel.CRITICAL: "\033[95m",   # Magenta
            LogLevel.SUCCESS: "\033[92m"     # Green
        }
        reset = "\033[0m"

        color = colors.get(entry.level, "")
        timestamp = entry.timestamp.split("T")[1].split(".")[0]

        print(f"{color}[{timestamp}] [{entry.level.value}] [{entry.source.value}] {entry.message}{reset}")

        if entry.error:
            print(f"{colors[LogLevel.ERROR]}  Error: {entry.error}{reset}")

    def _write_markdown(self, entry: LogEntry):
        """Write to Markdown log file."""
        with open(MASTER_LOG, "a", encoding="utf-8") as f:
            f.write(entry.to_markdown())

    def _write_json(self, entry: LogEntry):
        """Write to JSON log file."""
        try:
            with open(JSON_LOG, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logs = []

        logs.append(entry.to_dict())

        # Keep last 10000 entries
        if len(logs) > 10000:
            logs = logs[-10000:]

        with open(JSON_LOG, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)

    def _write_error_log(self, entry: LogEntry):
        """Write to dedicated error log."""
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(entry.to_markdown())

    # =========================================================================
    # Public Logging Methods
    # =========================================================================

    def debug(
        self,
        message: str,
        action: ActionType = ActionType.CUSTOM,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log debug message."""
        entry = self._create_entry(LogLevel.DEBUG, message, action, details=details)
        self._write_entry(entry)

    def info(
        self,
        message: str,
        action: ActionType = ActionType.CUSTOM,
        status: str = "OK",
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None
    ):
        """Log info message."""
        entry = self._create_entry(
            LogLevel.INFO, message, action, status, details, duration_ms=duration_ms
        )
        self._write_entry(entry)

    def success(
        self,
        message: str,
        action: ActionType = ActionType.CUSTOM,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None
    ):
        """Log success message."""
        entry = self._create_entry(
            LogLevel.SUCCESS, message, action, "SUCCESS", details, duration_ms=duration_ms
        )
        self._write_entry(entry)

    def warning(
        self,
        message: str,
        action: ActionType = ActionType.CUSTOM,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log warning message."""
        entry = self._create_entry(LogLevel.WARNING, message, action, "WARNING", details)
        self._write_entry(entry)

    def error(
        self,
        message: str,
        action: ActionType = ActionType.CUSTOM,
        error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log error message."""
        entry = self._create_entry(
            LogLevel.ERROR, message, action, "FAILED", details, error=error
        )
        self._write_entry(entry)

    def critical(
        self,
        message: str,
        action: ActionType = ActionType.CUSTOM,
        error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log critical message."""
        entry = self._create_entry(
            LogLevel.CRITICAL, message, action, "CRITICAL", details, error=error
        )
        self._write_entry(entry)

    # =========================================================================
    # Specialized Logging Methods
    # =========================================================================

    def task_started(self, task_id: str, task_type: str, details: Optional[Dict] = None):
        """Log task start."""
        self.info(
            f"Task started: {task_id}",
            action=ActionType.TASK_STARTED,
            details={"task_id": task_id, "task_type": task_type, **(details or {})}
        )

    def task_completed(self, task_id: str, duration_ms: float, details: Optional[Dict] = None):
        """Log task completion."""
        self.success(
            f"Task completed: {task_id}",
            action=ActionType.TASK_COMPLETED,
            details={"task_id": task_id, **(details or {})},
            duration_ms=duration_ms
        )

    def task_failed(self, task_id: str, error: Exception, details: Optional[Dict] = None):
        """Log task failure."""
        self.error(
            f"Task failed: {task_id}",
            action=ActionType.TASK_FAILED,
            error=error,
            details={"task_id": task_id, **(details or {})}
        )

    def api_request(self, endpoint: str, method: str, details: Optional[Dict] = None):
        """Log API request."""
        self.debug(
            f"API Request: {method} {endpoint}",
            action=ActionType.API_REQUEST,
            details={"endpoint": endpoint, "method": method, **(details or {})}
        )

    def api_response(self, endpoint: str, status_code: int, duration_ms: float):
        """Log API response."""
        level = LogLevel.SUCCESS if status_code < 400 else LogLevel.ERROR
        entry = self._create_entry(
            level,
            f"API Response: {status_code}",
            ActionType.API_RESPONSE,
            str(status_code),
            {"endpoint": endpoint, "status_code": status_code},
            duration_ms=duration_ms
        )
        self._write_entry(entry)

    def approval_requested(self, approval_id: str, approval_type: str, details: Optional[Dict] = None):
        """Log approval request."""
        self.info(
            f"Approval requested: {approval_id}",
            action=ActionType.APPROVAL_REQUESTED,
            details={"approval_id": approval_id, "type": approval_type, **(details or {})}
        )

    def approval_granted(self, approval_id: str, details: Optional[Dict] = None):
        """Log approval granted."""
        self.success(
            f"Approval granted: {approval_id}",
            action=ActionType.APPROVAL_GRANTED,
            details={"approval_id": approval_id, **(details or {})}
        )

    def approval_rejected(self, approval_id: str, reason: str, details: Optional[Dict] = None):
        """Log approval rejected."""
        self.warning(
            f"Approval rejected: {approval_id}",
            action=ActionType.APPROVAL_REJECTED,
            details={"approval_id": approval_id, "reason": reason, **(details or {})}
        )


# =============================================================================
# Decorators
# =============================================================================

def log_action(
    action: ActionType = ActionType.CUSTOM,
    source: ServiceSource = ServiceSource.UNKNOWN
):
    """
    Decorator to automatically log function execution.

    Usage:
        @log_action(action=ActionType.API_REQUEST, source=ServiceSource.ODOO_SERVER)
        async def create_invoice(data):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = get_logger(source)
            start_time = datetime.now()

            try:
                result = await func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds() * 1000
                logger.success(
                    f"{func.__name__} completed",
                    action=action,
                    duration_ms=duration
                )
                return result
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds() * 1000
                logger.error(
                    f"{func.__name__} failed",
                    action=action,
                    error=e,
                    details={"duration_ms": duration}
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = get_logger(source)
            start_time = datetime.now()

            try:
                result = func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds() * 1000
                logger.success(
                    f"{func.__name__} completed",
                    action=action,
                    duration_ms=duration
                )
                return result
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds() * 1000
                logger.error(
                    f"{func.__name__} failed",
                    action=action,
                    error=e,
                    details={"duration_ms": duration}
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# =============================================================================
# Factory Functions
# =============================================================================

def get_logger(source: ServiceSource = ServiceSource.UNKNOWN) -> AuditLogger:
    """Get or create a logger instance for a specific source."""
    logger = AuditLogger(source=source)
    logger.source = source  # Update source for existing singleton
    return logger


def create_service_logger(service_name: str) -> AuditLogger:
    """Create a logger for a named service."""
    # Map string names to enum
    source_map = {
        "odoo": ServiceSource.ODOO_SERVER,
        "social": ServiceSource.SOCIAL_MEDIA,
        "social_media": ServiceSource.SOCIAL_MEDIA,
        "x": ServiceSource.X_PUBLISHER,
        "x_publisher": ServiceSource.X_PUBLISHER,
        "ralph": ServiceSource.RALPH_LOOP,
        "ralph_loop": ServiceSource.RALPH_LOOP,
        "ceo_briefing": ServiceSource.CEO_BRIEFING,
        "error_handler": ServiceSource.ERROR_HANDLER,
        "system": ServiceSource.SYSTEM,
    }

    source = source_map.get(service_name.lower(), ServiceSource.UNKNOWN)
    return get_logger(source)


# =============================================================================
# Query Functions
# =============================================================================

def get_recent_logs(limit: int = 100, level: Optional[LogLevel] = None) -> List[Dict]:
    """Get recent log entries from JSON log."""
    try:
        with open(JSON_LOG, "r", encoding="utf-8") as f:
            logs = json.load(f)

        if level:
            logs = [l for l in logs if l.get("level") == level.value]

        return logs[-limit:]
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def get_error_summary(days: int = 7) -> Dict[str, Any]:
    """Get summary of errors from the past N days."""
    cutoff = datetime.now() - timedelta(days=days)
    logs = get_recent_logs(limit=10000)

    errors = [
        l for l in logs
        if l.get("level") in ("ERROR", "CRITICAL")
        and datetime.fromisoformat(l.get("timestamp", "")) > cutoff
    ]

    # Group by source
    by_source = {}
    for e in errors:
        source = e.get("source", "unknown")
        by_source[source] = by_source.get(source, 0) + 1

    # Group by action type
    by_action = {}
    for e in errors:
        action = e.get("action_type", "unknown")
        by_action[action] = by_action.get(action, 0) + 1

    return {
        "total_errors": len(errors),
        "period_days": days,
        "by_source": by_source,
        "by_action": by_action,
        "recent_errors": errors[-10:]
    }


# =============================================================================
# Module-level Logger Instance
# =============================================================================

# Default system logger
system_logger = get_logger(ServiceSource.SYSTEM)
