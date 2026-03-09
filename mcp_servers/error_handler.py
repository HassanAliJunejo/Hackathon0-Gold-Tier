"""
MCP Error Handler - Shared Error Handling Utilities
Gold Tier Autonomous Employee

Features:
- Retry logic with exponential backoff (3 attempts)
- Timeout handling with configurable limits
- Fallback logging for all failures
- Failed task recovery to /Needs_Action
"""

import os
import json
import sys
import asyncio
import functools
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, Callable, TypeVar, ParamSpec
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field, asdict

# Import universal logger
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from logger import get_logger, ServiceSource, ActionType

# =============================================================================
# Configuration
# =============================================================================

BASE_DIR = Path(__file__).parent.parent
NEEDS_ACTION_DIR = BASE_DIR / "Needs_Action"
LOGS_DIR = BASE_DIR / "Logs"
FALLBACK_LOG = LOGS_DIR / "error_fallback.md"

# Default settings
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30.0  # seconds
DEFAULT_RETRY_DELAY = 1.0  # seconds
MAX_BACKOFF = 30.0  # maximum backoff time


# =============================================================================
# Enums and Data Classes
# =============================================================================

class ErrorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    API = "api"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay: float = DEFAULT_RETRY_DELAY
    max_delay: float = MAX_BACKOFF
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: tuple = (Exception,)
    no_retry_on: tuple = ()


@dataclass
class TimeoutConfig:
    """Configuration for timeout behavior."""
    connect_timeout: float = 10.0
    read_timeout: float = DEFAULT_TIMEOUT
    write_timeout: float = DEFAULT_TIMEOUT
    total_timeout: float = 60.0


@dataclass
class ErrorContext:
    """Context information for an error."""
    service: str
    action: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    task_ref: Optional[str] = None
    approval_id: Optional[str] = None
    request_data: Optional[Dict[str, Any]] = None
    attempt: int = 1
    max_attempts: int = DEFAULT_MAX_RETRIES


@dataclass
class ErrorResult:
    """Result of an error handling operation."""
    success: bool
    error_message: str
    error_category: ErrorCategory
    severity: ErrorSeverity
    retry_scheduled: bool = False
    needs_action_file: Optional[str] = None
    fallback_logged: bool = False
    context: Optional[ErrorContext] = None


# =============================================================================
# Error Classification
# =============================================================================

class ErrorClassifier:
    """Classifies errors by category and severity."""

    NETWORK_ERRORS = (
        "ConnectionError",
        "ConnectTimeout",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "SSLError",
        "ProxyError",
    )

    TIMEOUT_ERRORS = (
        "TimeoutError",
        "ReadTimeout",
        "WriteTimeout",
        "asyncio.TimeoutError",
    )

    RATE_LIMIT_INDICATORS = (
        "rate limit",
        "too many requests",
        "429",
        "throttl",
    )

    AUTH_INDICATORS = (
        "unauthorized",
        "authentication",
        "401",
        "403",
        "invalid token",
        "expired token",
    )

    @classmethod
    def classify(cls, error: Exception) -> tuple[ErrorCategory, ErrorSeverity]:
        """Classify an error by category and severity."""
        error_type = type(error).__name__
        error_msg = str(error).lower()

        # Check timeout
        if error_type in cls.TIMEOUT_ERRORS or "timeout" in error_msg:
            return ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM

        # Check network errors
        if error_type in cls.NETWORK_ERRORS or "connection" in error_msg:
            return ErrorCategory.NETWORK, ErrorSeverity.MEDIUM

        # Check rate limiting
        if any(indicator in error_msg for indicator in cls.RATE_LIMIT_INDICATORS):
            return ErrorCategory.RATE_LIMIT, ErrorSeverity.LOW

        # Check authentication
        if any(indicator in error_msg for indicator in cls.AUTH_INDICATORS):
            return ErrorCategory.AUTHENTICATION, ErrorSeverity.HIGH

        # Check validation
        if "validation" in error_msg or "invalid" in error_msg:
            return ErrorCategory.VALIDATION, ErrorSeverity.LOW

        # Check API errors
        if "api" in error_msg or "response" in error_msg:
            return ErrorCategory.API, ErrorSeverity.MEDIUM

        return ErrorCategory.UNKNOWN, ErrorSeverity.MEDIUM

    @classmethod
    def should_retry(cls, error: Exception, category: ErrorCategory) -> bool:
        """Determine if an error should trigger a retry."""
        # Don't retry authentication or validation errors
        if category in (ErrorCategory.AUTHENTICATION, ErrorCategory.VALIDATION):
            return False

        # Retry network, timeout, and rate limit errors
        if category in (ErrorCategory.NETWORK, ErrorCategory.TIMEOUT, ErrorCategory.RATE_LIMIT):
            return True

        # Retry API errors (might be transient)
        if category == ErrorCategory.API:
            return True

        return False


# =============================================================================
# Fallback Logger
# =============================================================================

class FallbackLogger:
    """Logs errors to fallback file when primary logging fails."""

    def __init__(self, log_file: Path = FALLBACK_LOG):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        error: Exception,
        context: ErrorContext,
        category: ErrorCategory,
        severity: ErrorSeverity
    ) -> bool:
        """Log error to fallback file."""
        try:
            timestamp = datetime.now().isoformat()

            entry = f"""
---

## [{severity.value.upper()}] {context.service} - {context.action}

| Field | Value |
|-------|-------|
| **Timestamp** | {timestamp} |
| **Service** | {context.service} |
| **Action** | {context.action} |
| **Error Category** | {category.value} |
| **Severity** | {severity.value} |
| **Attempt** | {context.attempt}/{context.max_attempts} |
| **Task Reference** | {context.task_ref or 'N/A'} |
| **Approval ID** | {context.approval_id or 'N/A'} |

### Error Details

```
{type(error).__name__}: {str(error)}
```

### Stack Trace

```
{traceback.format_exc()}
```

### Request Data

```json
{json.dumps(context.request_data, indent=2) if context.request_data else 'N/A'}
```

"""

            mode = "a" if self.log_file.exists() else "w"
            if mode == "w":
                header = """# Error Fallback Log

All unhandled errors and fallback events are logged here for audit and debugging.

"""
                entry = header + entry

            with open(self.log_file, mode, encoding="utf-8") as f:
                f.write(entry)

            return True

        except Exception:
            # Last resort: print to console
            print(f"[FALLBACK LOG FAILED] {context.service}: {error}")
            return False


# =============================================================================
# Needs Action Recovery
# =============================================================================

class NeedsActionRecovery:
    """Saves failed tasks back to /Needs_Action for retry."""

    def __init__(self, needs_action_dir: Path = NEEDS_ACTION_DIR):
        self.needs_action_dir = needs_action_dir
        self.needs_action_dir.mkdir(parents=True, exist_ok=True)

    def save_for_retry(
        self,
        context: ErrorContext,
        error: Exception,
        category: ErrorCategory,
        original_request: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save failed task to /Needs_Action with Retry Required status."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        task_id = f"RETRY-{context.service.upper()}-{timestamp}"

        content = f"""# Retry Required: {context.action}

## Task Information

| Field | Value |
|-------|-------|
| **Task ID** | {task_id} |
| **Original Service** | {context.service} |
| **Original Action** | {context.action} |
| **Created** | {datetime.now().isoformat()} |
| **Status** | RETRY REQUIRED |
| **Error Category** | {category.value} |
| **Attempts Made** | {context.attempt} |
| **Original Task Ref** | {context.task_ref or 'N/A'} |
| **Original Approval ID** | {context.approval_id or 'N/A'} |

## Error Details

**Error Type:** `{type(error).__name__}`

**Error Message:**
```
{str(error)}
```

## Original Request Data

```json
{json.dumps(original_request or context.request_data or {}, indent=2)}
```

## Recovery Instructions

1. Review the error details above
2. Fix any underlying issues (credentials, network, etc.)
3. Remove this file once the task is manually completed
4. Or wait for RALPH loop to automatically retry

---

*Generated by MCP Error Handler*
*This task will be automatically retried by the RALPH loop*
"""

        file_path = self.needs_action_dir / f"{task_id}.md"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return str(file_path)


# =============================================================================
# Retry Decorator with Enhanced Error Handling
# =============================================================================

P = ParamSpec("P")
T = TypeVar("T")


def with_enhanced_retry(
    service: str,
    action: str,
    config: Optional[RetryConfig] = None,
    timeout_config: Optional[TimeoutConfig] = None,
    save_on_failure: bool = True
):
    """
    Enhanced retry decorator with timeout, logging, and failure recovery.

    Args:
        service: Name of the service (e.g., "odoo", "social", "x_publisher")
        action: Name of the action being performed
        config: Retry configuration
        timeout_config: Timeout configuration
        save_on_failure: Whether to save failed tasks to /Needs_Action
    """
    if config is None:
        config = RetryConfig()
    if timeout_config is None:
        timeout_config = TimeoutConfig()

    fallback_logger = FallbackLogger()
    recovery = NeedsActionRecovery()

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Optional[Exception] = None
            context = ErrorContext(
                service=service,
                action=action,
                max_attempts=config.max_retries,
                request_data=kwargs.copy() if kwargs else None
            )

            # Extract task_ref and approval_id from kwargs if present
            context.task_ref = kwargs.get("task_ref")
            context.approval_id = kwargs.get("approval_id")

            for attempt in range(1, config.max_retries + 1):
                context.attempt = attempt

                try:
                    # Apply timeout
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=timeout_config.total_timeout
                    )
                    return result

                except asyncio.TimeoutError as e:
                    last_exception = e
                    category, severity = ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM

                    print(f"[{service}] {action} - Timeout on attempt {attempt}/{config.max_retries}")

                    # Log to fallback
                    fallback_logger.log(e, context, category, severity)

                    if attempt < config.max_retries:
                        delay = min(
                            config.base_delay * (config.exponential_base ** (attempt - 1)),
                            config.max_delay
                        )
                        if config.jitter:
                            import random
                            delay *= (0.5 + random.random())
                        await asyncio.sleep(delay)
                    continue

                except config.no_retry_on as e:
                    # Don't retry these errors
                    category, severity = ErrorClassifier.classify(e)
                    fallback_logger.log(e, context, category, severity)
                    raise

                except config.retry_on as e:
                    last_exception = e
                    category, severity = ErrorClassifier.classify(e)

                    print(f"[{service}] {action} - Error on attempt {attempt}/{config.max_retries}: {e}")

                    # Log to fallback
                    fallback_logger.log(e, context, category, severity)

                    # Check if we should retry
                    if not ErrorClassifier.should_retry(e, category):
                        break

                    if attempt < config.max_retries:
                        delay = min(
                            config.base_delay * (config.exponential_base ** (attempt - 1)),
                            config.max_delay
                        )
                        if config.jitter:
                            import random
                            delay *= (0.5 + random.random())
                        await asyncio.sleep(delay)
                    continue

                except Exception as e:
                    last_exception = e
                    category, severity = ErrorClassifier.classify(e)
                    fallback_logger.log(e, context, category, severity)
                    break

            # All retries exhausted - save to Needs_Action
            if last_exception and save_on_failure:
                category, severity = ErrorClassifier.classify(last_exception)
                needs_action_file = recovery.save_for_retry(
                    context=context,
                    error=last_exception,
                    category=category,
                    original_request=kwargs
                )
                print(f"[{service}] {action} - Failed after {config.max_retries} attempts. "
                      f"Saved to: {needs_action_file}")

            if last_exception:
                raise last_exception

        return wrapper
    return decorator


# =============================================================================
# Timeout Wrapper
# =============================================================================

async def with_timeout(
    coro,
    timeout: float = DEFAULT_TIMEOUT,
    service: str = "unknown",
    action: str = "unknown"
):
    """
    Execute a coroutine with timeout and proper error handling.

    Args:
        coro: Coroutine to execute
        timeout: Timeout in seconds
        service: Service name for logging
        action: Action name for logging

    Returns:
        Result of the coroutine

    Raises:
        TimeoutError: If the operation times out
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        fallback_logger = FallbackLogger()
        context = ErrorContext(service=service, action=action)
        error = TimeoutError(f"Operation timed out after {timeout}s")
        fallback_logger.log(error, context, ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM)
        raise error


# =============================================================================
# Error Handler Class (for use in request handlers)
# =============================================================================

class MCPErrorHandler:
    """
    Centralized error handler for MCP servers.

    Usage:
        handler = MCPErrorHandler("odoo")

        try:
            result = await some_operation()
        except Exception as e:
            return handler.handle(e, "create_invoice", request_data=request.dict())
    """

    def __init__(self, service: str):
        self.service = service
        self.fallback_logger = FallbackLogger()
        self.recovery = NeedsActionRecovery()
        # Initialize universal audit logger
        self.audit_logger = get_logger(ServiceSource.ERROR_HANDLER)

    def handle(
        self,
        error: Exception,
        action: str,
        request_data: Optional[Dict[str, Any]] = None,
        task_ref: Optional[str] = None,
        approval_id: Optional[str] = None,
        save_for_retry: bool = True
    ) -> ErrorResult:
        """
        Handle an error with logging and optional retry scheduling.

        Args:
            error: The exception that occurred
            action: The action that was being performed
            request_data: Original request data
            task_ref: Task reference if applicable
            approval_id: Approval ID if applicable
            save_for_retry: Whether to save to /Needs_Action

        Returns:
            ErrorResult with details about the handling
        """
        category, severity = ErrorClassifier.classify(error)

        context = ErrorContext(
            service=self.service,
            action=action,
            task_ref=task_ref,
            approval_id=approval_id,
            request_data=request_data
        )

        # Log to fallback
        fallback_logged = self.fallback_logger.log(error, context, category, severity)

        # Save to Needs_Action if appropriate
        needs_action_file = None
        if save_for_retry and ErrorClassifier.should_retry(error, category):
            needs_action_file = self.recovery.save_for_retry(
                context=context,
                error=error,
                category=category,
                original_request=request_data
            )

        # Log to universal audit logger
        self.audit_logger.error(
            f"[{self.service}] {action} failed",
            action=ActionType.TASK_FAILED,
            error=error,
            details={
                "service": self.service,
                "action": action,
                "category": category.value,
                "severity": severity.value,
                "retry_scheduled": needs_action_file is not None
            }
        )

        return ErrorResult(
            success=False,
            error_message=str(error),
            error_category=category,
            severity=severity,
            retry_scheduled=needs_action_file is not None,
            needs_action_file=needs_action_file,
            fallback_logged=fallback_logged,
            context=context
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def create_error_handler(service: str) -> MCPErrorHandler:
    """Create an error handler for a service."""
    return MCPErrorHandler(service)


def get_retry_decorator(
    service: str,
    action: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout: float = DEFAULT_TIMEOUT
):
    """Get a pre-configured retry decorator."""
    return with_enhanced_retry(
        service=service,
        action=action,
        config=RetryConfig(max_retries=max_retries),
        timeout_config=TimeoutConfig(total_timeout=timeout)
    )
