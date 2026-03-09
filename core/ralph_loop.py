"""
RALPH Loop - Reasoning Agent Loop for Processing Hierarchical tasks
Gold Tier Autonomous Employee - Core Execution Engine

Continuously processes tasks until all work is complete.
"""

import os
import json
import asyncio
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

BASE_DIR = Path(__file__).parent.parent
NEEDS_ACTION_DIR = BASE_DIR / "Needs_Action"
PENDING_DIR = BASE_DIR / "Pending_Approval"
APPROVED_DIR = BASE_DIR / "Approved"
REJECTED_DIR = BASE_DIR / "Rejected"
REPORTS_DIR = BASE_DIR / "Reports"
LOG_DIR = BASE_DIR / "Logs"

LOG_FILE = LOG_DIR / "ralph_loop.md"

# Safety limits
MAX_ITERATIONS = 100
MAX_ERRORS_CONSECUTIVE = 5
ITERATION_DELAY = 2  # seconds between iterations
ERROR_BACKOFF = 5  # seconds after error

# MCP Server endpoints
MCP_SERVERS = {
    "odoo": os.getenv("MCP_ODOO_URL", "http://localhost:8001"),
    "social": os.getenv("MCP_SOCIAL_URL", "http://localhost:8002"),
    "x_publisher": os.getenv("MCP_X_URL", "http://localhost:8003"),
}


# =============================================================================
# Enums and Data Classes
# =============================================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType(str, Enum):
    EMAIL = "email"
    SOCIAL_POST = "social_post"
    X_TWEET = "x_tweet"
    ODOO_ACTION = "odoo_action"
    REPORT = "report"
    GENERIC = "generic"


@dataclass
class Task:
    id: str
    type: TaskType
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    approval_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class LoopState:
    iteration: int = 0
    consecutive_errors: int = 0
    tasks_processed: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    last_action: str = "initialized"
    should_stop: bool = False
    stop_reason: Optional[str] = None


# =============================================================================
# Logging
# =============================================================================

class RalphLogger:
    """Structured logging for RALPH loop."""

    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._init_log()

    def _init_log(self):
        """Initialize log file with header."""
        if not self.log_file.exists():
            header = """# RALPH Loop Execution Log

Reasoning Agent Loop for Processing Hierarchical tasks

---

"""
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write(header)

    def log(
        self,
        level: str,
        action: str,
        details: Dict[str, Any],
        error: Optional[str] = None
    ):
        """Log an action to the log file."""
        timestamp = datetime.now().isoformat()

        entry = f"""
## [{level}] {action}

| Field | Value |
|-------|-------|
| **Timestamp** | {timestamp} |
| **Action** | {action} |
| **Details** | {json.dumps(details, indent=2)} |
"""
        if error:
            entry += f"| **Error** | {error} |\n"

        entry += "\n---\n"

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(entry)

        # Also print to console
        print(f"[{timestamp}] [{level}] {action}")

    def info(self, action: str, details: Dict[str, Any]):
        self.log("INFO", action, details)

    def warning(self, action: str, details: Dict[str, Any]):
        self.log("WARNING", action, details)

    def error(self, action: str, details: Dict[str, Any], error: str):
        self.log("ERROR", action, details, error)

    def success(self, action: str, details: Dict[str, Any]):
        self.log("SUCCESS", action, details)


# =============================================================================
# Task Scanner
# =============================================================================

class TaskScanner:
    """Scans directories for tasks requiring action."""

    def __init__(self, logger: RalphLogger):
        self.logger = logger

    def scan_needs_action(self) -> List[Task]:
        """Scan /Needs_Action folder for new tasks."""
        NEEDS_ACTION_DIR.mkdir(parents=True, exist_ok=True)
        tasks = []

        for file in NEEDS_ACTION_DIR.glob("*.md"):
            try:
                content = file.read_text(encoding="utf-8")
                task = self._parse_task_file(file.stem, content)
                if task:
                    tasks.append(task)
            except Exception as e:
                self.logger.error(
                    "Parse Task File",
                    {"file": str(file)},
                    str(e)
                )

        return tasks

    def scan_pending_approvals(self) -> List[Dict[str, Any]]:
        """Scan /Pending_Approval for items awaiting approval."""
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        pending = []

        for file in PENDING_DIR.glob("APPROVAL-*.md"):
            pending.append({
                "approval_id": file.stem,
                "file": str(file),
                "created": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
            })

        return pending

    def scan_approved(self) -> List[Dict[str, Any]]:
        """Scan /Approved for items ready to execute."""
        APPROVED_DIR.mkdir(parents=True, exist_ok=True)
        approved = []

        for file in APPROVED_DIR.glob("APPROVAL-*.md"):
            approved.append({
                "approval_id": file.stem,
                "file": str(file),
                "approved_at": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
            })

        return approved

    def _parse_task_file(self, task_id: str, content: str) -> Optional[Task]:
        """Parse a task markdown file into a Task object."""
        import re

        # Extract title
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else task_id

        # Detect task type
        task_type = TaskType.GENERIC
        content_lower = content.lower()
        if "tweet" in content_lower or "x post" in content_lower:
            task_type = TaskType.X_TWEET
        elif "facebook" in content_lower or "instagram" in content_lower:
            task_type = TaskType.SOCIAL_POST
        elif "email" in content_lower:
            task_type = TaskType.EMAIL
        elif "odoo" in content_lower or "invoice" in content_lower:
            task_type = TaskType.ODOO_ACTION
        elif "report" in content_lower:
            task_type = TaskType.REPORT

        # Extract dependencies
        deps_match = re.search(r"dependencies?:\s*\[(.+?)\]", content, re.IGNORECASE)
        dependencies = []
        if deps_match:
            dependencies = [d.strip() for d in deps_match.group(1).split(",")]

        return Task(
            id=task_id,
            type=task_type,
            title=title,
            description=content,
            dependencies=dependencies
        )


# =============================================================================
# Reasoning Engine
# =============================================================================

class ReasoningEngine:
    """Determines next actions based on system state."""

    def __init__(self, logger: RalphLogger):
        self.logger = logger

    def evaluate(
        self,
        tasks: List[Task],
        pending_approvals: List[Dict],
        approved_items: List[Dict],
        state: LoopState
    ) -> Dict[str, Any]:
        """Evaluate system state and determine next action."""

        # Priority 1: Execute approved items
        if approved_items:
            return {
                "action": "execute_approved",
                "target": approved_items[0],
                "reason": f"Found {len(approved_items)} approved item(s) ready for execution"
            }

        # Priority 2: Process new tasks
        actionable_tasks = [t for t in tasks if self._can_execute(t, tasks)]
        if actionable_tasks:
            task = actionable_tasks[0]
            return {
                "action": "process_task",
                "target": task,
                "reason": f"Processing task: {task.title}"
            }

        # Priority 3: Check if waiting on approvals
        if pending_approvals:
            return {
                "action": "wait_approval",
                "target": pending_approvals,
                "reason": f"Waiting on {len(pending_approvals)} approval(s)"
            }

        # Priority 4: Check for blocked tasks
        blocked_tasks = [t for t in tasks if not self._can_execute(t, tasks)]
        if blocked_tasks:
            return {
                "action": "resolve_dependencies",
                "target": blocked_tasks,
                "reason": f"{len(blocked_tasks)} task(s) blocked by dependencies"
            }

        # Nothing to do
        return {
            "action": "idle",
            "target": None,
            "reason": "No actionable items found"
        }

    def _can_execute(self, task: Task, all_tasks: List[Task]) -> bool:
        """Check if a task's dependencies are satisfied."""
        if not task.dependencies:
            return True

        completed_ids = {t.id for t in all_tasks if t.status == TaskStatus.COMPLETED}
        return all(dep in completed_ids for dep in task.dependencies)


# =============================================================================
# Task Executor
# =============================================================================

class TaskExecutor:
    """Executes tasks by calling appropriate MCP servers."""

    def __init__(self, logger: RalphLogger):
        self.logger = logger
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def execute_approved(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an approved item."""
        approval_id = approval["approval_id"]

        try:
            # Determine which server to call based on approval ID
            if "APPROVAL-X-" in approval_id:
                return await self._publish_x_tweet(approval_id)
            elif "APPROVAL-" in approval_id:
                return await self._publish_social_post(approval_id)
            else:
                return {"success": False, "error": "Unknown approval type"}

        except Exception as e:
            self.logger.error(
                "Execute Approved",
                {"approval_id": approval_id},
                str(e)
            )
            return {"success": False, "error": str(e)}

    async def process_task(self, task: Task) -> Dict[str, Any]:
        """Process a task based on its type."""
        try:
            if task.type == TaskType.X_TWEET:
                return await self._create_x_draft(task)
            elif task.type == TaskType.SOCIAL_POST:
                return await self._create_social_draft(task)
            elif task.type == TaskType.ODOO_ACTION:
                return await self._execute_odoo_action(task)
            elif task.type == TaskType.REPORT:
                return await self._generate_report(task)
            else:
                return await self._handle_generic_task(task)

        except Exception as e:
            self.logger.error(
                "Process Task",
                {"task_id": task.id, "type": task.type.value},
                str(e)
            )
            return {"success": False, "error": str(e)}

    async def _publish_x_tweet(self, approval_id: str) -> Dict[str, Any]:
        """Publish approved X tweet."""
        url = f"{MCP_SERVERS['x_publisher']}/publish-tweet"
        response = await self.client.post(url, json={"approval_id": approval_id})
        return response.json()

    async def _publish_social_post(self, approval_id: str) -> Dict[str, Any]:
        """Publish approved social media post."""
        url = f"{MCP_SERVERS['social']}/publish-post"
        response = await self.client.post(url, json={"approval_id": approval_id})
        return response.json()

    async def _create_x_draft(self, task: Task) -> Dict[str, Any]:
        """Create X tweet draft for approval."""
        # First generate tweet content
        generate_url = f"{MCP_SERVERS['x_publisher']}/generate-tweet"
        gen_response = await self.client.post(generate_url, json={
            "topic": task.title,
            "tone": "professional",
            "include_hashtags": True
        })
        generated = gen_response.json()

        if not generated.get("success"):
            return generated

        # Create draft for approval
        draft_url = f"{MCP_SERVERS['x_publisher']}/draft-tweet"
        draft_response = await self.client.post(draft_url, json={
            "content": generated["content"],
            "tweet_type": "standard",
            "task_ref": f"TASK-{task.id}",
            "reason": task.description[:200]
        })

        return draft_response.json()

    async def _create_social_draft(self, task: Task) -> Dict[str, Any]:
        """Create social media post draft for approval."""
        platform = "facebook"
        if "instagram" in task.description.lower():
            platform = "instagram"

        url = f"{MCP_SERVERS['social']}/draft-post"
        response = await self.client.post(url, json={
            "platform": platform,
            "message": task.title,
            "task_ref": f"TASK-{task.id}",
            "reason": task.description[:200]
        })

        return response.json()

    async def _execute_odoo_action(self, task: Task) -> Dict[str, Any]:
        """Execute Odoo-related action."""
        # Placeholder - implement based on task content
        self.logger.info("Odoo Action", {"task": task.id, "status": "not_implemented"})
        return {"success": True, "message": "Odoo action logged for manual review"}

    async def _generate_report(self, task: Task) -> Dict[str, Any]:
        """Generate a report."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        report_content = f"""# Report: {task.title}

**Generated:** {datetime.now().isoformat()}
**Task ID:** {task.id}

## Description

{task.description}

## Status

Report generated successfully.

---

*Generated by RALPH Loop*
"""

        report_file = REPORTS_DIR / f"report_{task.id}_{datetime.now().strftime('%Y%m%d')}.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

        return {"success": True, "file": str(report_file)}

    async def _handle_generic_task(self, task: Task) -> Dict[str, Any]:
        """Handle generic task - log for manual review."""
        self.logger.info("Generic Task", {
            "task_id": task.id,
            "title": task.title,
            "status": "logged_for_review"
        })
        return {"success": True, "message": "Task logged for manual review"}


# =============================================================================
# Error Handler
# =============================================================================

class ErrorHandler:
    """Handles errors and implements recovery strategies."""

    def __init__(self, logger: RalphLogger):
        self.logger = logger

    def handle(self, error: Exception, context: Dict[str, Any], state: LoopState) -> LoopState:
        """Handle an error and update state."""
        state.consecutive_errors += 1

        self.logger.error(
            "Error Occurred",
            {
                "context": context,
                "consecutive_errors": state.consecutive_errors,
                "iteration": state.iteration
            },
            str(error)
        )

        # Check if we should stop due to too many errors
        if state.consecutive_errors >= MAX_ERRORS_CONSECUTIVE:
            state.should_stop = True
            state.stop_reason = f"Too many consecutive errors ({state.consecutive_errors})"

        return state

    def reset_error_count(self, state: LoopState) -> LoopState:
        """Reset consecutive error count after successful action."""
        state.consecutive_errors = 0
        return state


# =============================================================================
# RALPH Loop - Main Controller
# =============================================================================

class RalphLoop:
    """
    Main autonomous loop controller.

    Continuously processes tasks until:
    - All tasks are resolved
    - No pending approvals remain
    - Max iterations reached
    - Too many consecutive errors
    """

    def __init__(self):
        self.logger = RalphLogger(LOG_FILE)
        self.scanner = TaskScanner(self.logger)
        self.reasoning = ReasoningEngine(self.logger)
        self.executor = TaskExecutor(self.logger)
        self.error_handler = ErrorHandler(self.logger)
        self.state = LoopState()

    async def run(self):
        """Main loop execution."""
        self.logger.info("RALPH Loop Started", {
            "max_iterations": MAX_ITERATIONS,
            "max_consecutive_errors": MAX_ERRORS_CONSECUTIVE
        })

        try:
            while not self.state.should_stop:
                await self._iteration()

                # Check stop conditions
                if self._should_stop():
                    break

                # Delay between iterations
                await asyncio.sleep(ITERATION_DELAY)

        except KeyboardInterrupt:
            self.state.stop_reason = "User interrupted"
            self.logger.warning("Loop Interrupted", {"reason": "KeyboardInterrupt"})

        except Exception as e:
            self.state.stop_reason = f"Unexpected error: {str(e)}"
            self.logger.error("Loop Failed", {}, str(e))

        finally:
            await self.executor.close()
            self._log_final_state()

    async def _iteration(self):
        """Execute one iteration of the loop."""
        self.state.iteration += 1

        self.logger.info(f"Iteration {self.state.iteration}", {
            "tasks_processed": self.state.tasks_processed,
            "tasks_completed": self.state.tasks_completed
        })

        try:
            # Step 1: Scan for work
            tasks = self.scanner.scan_needs_action()
            pending_approvals = self.scanner.scan_pending_approvals()
            approved_items = self.scanner.scan_approved()

            # Step 2: Reasoning - determine next action
            decision = self.reasoning.evaluate(
                tasks, pending_approvals, approved_items, self.state
            )

            self.logger.info("Reasoning Decision", decision)

            # Step 3: Execute based on decision
            result = await self._execute_decision(decision)

            # Step 4: Update state
            if result.get("success"):
                self.state = self.error_handler.reset_error_count(self.state)
                self.state.tasks_processed += 1

                if decision["action"] == "execute_approved":
                    self.state.tasks_completed += 1

            self.state.last_action = decision["action"]

        except Exception as e:
            self.state = self.error_handler.handle(
                e,
                {"iteration": self.state.iteration},
                self.state
            )
            await asyncio.sleep(ERROR_BACKOFF)

    async def _execute_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the reasoning engine's decision."""
        action = decision["action"]

        if action == "execute_approved":
            result = await self.executor.execute_approved(decision["target"])
            self.logger.success("Executed Approved Item", {
                "approval_id": decision["target"]["approval_id"],
                "result": result
            })
            return result

        elif action == "process_task":
            task = decision["target"]
            result = await self.executor.process_task(task)
            self.logger.info("Processed Task", {
                "task_id": task.id,
                "result": result
            })
            return result

        elif action == "wait_approval":
            self.logger.info("Waiting for Approvals", {
                "pending_count": len(decision["target"])
            })
            return {"success": True, "action": "waiting"}

        elif action == "resolve_dependencies":
            self.logger.info("Resolving Dependencies", {
                "blocked_count": len(decision["target"])
            })
            return {"success": True, "action": "resolving"}

        elif action == "idle":
            self.logger.info("Idle", {"reason": decision["reason"]})
            return {"success": True, "action": "idle"}

        return {"success": False, "error": f"Unknown action: {action}"}

    def _should_stop(self) -> bool:
        """Check if loop should stop."""
        # Max iterations reached
        if self.state.iteration >= MAX_ITERATIONS:
            self.state.should_stop = True
            self.state.stop_reason = f"Max iterations reached ({MAX_ITERATIONS})"
            return True

        # Check if all work is complete
        tasks = self.scanner.scan_needs_action()
        pending = self.scanner.scan_pending_approvals()
        approved = self.scanner.scan_approved()

        if not tasks and not pending and not approved:
            self.state.should_stop = True
            self.state.stop_reason = "All tasks resolved, no pending approvals"
            return True

        # Check consecutive errors
        if self.state.consecutive_errors >= MAX_ERRORS_CONSECUTIVE:
            return True

        return False

    def _log_final_state(self):
        """Log final state summary."""
        duration = datetime.now() - datetime.fromisoformat(self.state.start_time)

        summary = {
            "total_iterations": self.state.iteration,
            "tasks_processed": self.state.tasks_processed,
            "tasks_completed": self.state.tasks_completed,
            "tasks_failed": self.state.tasks_failed,
            "consecutive_errors": self.state.consecutive_errors,
            "duration_seconds": duration.total_seconds(),
            "stop_reason": self.state.stop_reason
        }

        self.logger.info("RALPH Loop Completed", summary)

        # Save summary to Reports
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        summary_file = REPORTS_DIR / f"ralph_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        summary_content = f"""# RALPH Loop Execution Summary

**Completed:** {datetime.now().isoformat()}
**Duration:** {duration.total_seconds():.2f} seconds

## Statistics

| Metric | Value |
|--------|-------|
| **Total Iterations** | {self.state.iteration} |
| **Tasks Processed** | {self.state.tasks_processed} |
| **Tasks Completed** | {self.state.tasks_completed} |
| **Tasks Failed** | {self.state.tasks_failed} |
| **Stop Reason** | {self.state.stop_reason} |

## Configuration

| Setting | Value |
|---------|-------|
| Max Iterations | {MAX_ITERATIONS} |
| Max Consecutive Errors | {MAX_ERRORS_CONSECUTIVE} |
| Iteration Delay | {ITERATION_DELAY}s |

---

*Generated by RALPH Loop*
"""

        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(summary_content)

        print(f"\n{'='*50}")
        print("RALPH Loop Completed")
        print(f"{'='*50}")
        print(f"Iterations: {self.state.iteration}")
        print(f"Tasks Completed: {self.state.tasks_completed}")
        print(f"Stop Reason: {self.state.stop_reason}")
        print(f"Summary: {summary_file}")
        print(f"{'='*50}\n")


# =============================================================================
# Entry Point
# =============================================================================

async def main():
    """Main entry point."""
    # Ensure directories exist
    for dir_path in [NEEDS_ACTION_DIR, PENDING_DIR, APPROVED_DIR, REJECTED_DIR, REPORTS_DIR, LOG_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)

    loop = RalphLoop()
    await loop.run()


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                    RALPH LOOP v1.0                        ║
    ║   Reasoning Agent Loop for Processing Hierarchical tasks  ║
    ║              Gold Tier Autonomous Employee                ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    asyncio.run(main())
