"""
MCP Social Media Publisher - Gold Tier Autonomous Employee
FastAPI server for Facebook & Instagram posting with approval workflow
"""

import os
import json
import httpx
import asyncio
from datetime import datetime
from typing import Optional
from pathlib import Path
from functools import wraps
from enum import Enum

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Import shared error handler
from error_handler import (
    MCPErrorHandler,
    with_enhanced_retry,
    RetryConfig,
    TimeoutConfig,
    ErrorCategory,
    ErrorSeverity,
    with_timeout
)

# Import universal logger
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from logger import (
    get_logger,
    ServiceSource,
    ActionType,
    log_action as log_action_decorator
)

load_dotenv()

# Initialize universal logger
audit_logger = get_logger(ServiceSource.SOCIAL_MEDIA)

# =============================================================================
# Configuration
# =============================================================================

FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN", "")
IG_BUSINESS_ID = os.getenv("IG_BUSINESS_ID", "")
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")

MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "Reports"
PENDING_DIR = BASE_DIR / "Pending_Approval"
APPROVED_DIR = BASE_DIR / "Approved"
REJECTED_DIR = BASE_DIR / "Rejected"
SUMMARY_FILE = REPORTS_DIR / "social_summary.md"
LOG_FILE = BASE_DIR / "Logs" / "social_log.md"

# Initialize error handler
error_handler = MCPErrorHandler("social_media")

# Timeout configuration
TIMEOUT_CONFIG = TimeoutConfig(
    connect_timeout=10.0,
    read_timeout=30.0,
    total_timeout=60.0
)

# =============================================================================
# FastAPI App
# =============================================================================

app = FastAPI(
    title="MCP Social Media Publisher",
    description="Gold Tier Autonomous Employee - Social Media Integration with Approval Workflow",
    version="1.0.0"
)

# =============================================================================
# Enums
# =============================================================================

class Platform(str, Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# =============================================================================
# Pydantic Models
# =============================================================================

class CreatePostRequest(BaseModel):
    platform: Platform = Field(..., description="Target platform: facebook or instagram")
    message: str = Field(..., min_length=1, max_length=2200, description="Post content")
    image_url: Optional[str] = Field(default=None, description="Image URL for media posts")
    task_ref: str = Field(..., description="TASK-XXX reference for tracking")
    reason: str = Field(..., description="Why this post is being made")


class PostResponse(BaseModel):
    success: bool
    message: str
    approval_id: Optional[str] = None
    post_id: Optional[str] = None
    data: Optional[dict] = None


class PublishRequest(BaseModel):
    approval_id: str = Field(..., description="APPROVAL-XXX from approved folder")


class PostSummary(BaseModel):
    success: bool
    total_posts: int
    facebook_posts: int
    instagram_posts: int
    pending_approvals: int
    recent_posts: list[dict]


# =============================================================================
# Logging Utility
# =============================================================================

async def log_action(
    action: str,
    status: str,
    details: dict,
    error: Optional[str] = None
) -> None:
    """Log action to social_log.md for audit trail."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat()

    log_entry = f"""
---

## {action}

| Field | Value |
|-------|-------|
| **Timestamp** | {timestamp} |
| **Status** | {status} |
| **Details** | {json.dumps(details, indent=2)} |
"""

    if error:
        log_entry += f"| **Error** | {error} |\n"

    log_entry += "\n"

    mode = "a" if LOG_FILE.exists() else "w"
    if mode == "w":
        header = "# Social Media Action Log\n\nAll social media actions are logged for audit compliance.\n\n"
        log_entry = header + log_entry

    with open(LOG_FILE, mode, encoding="utf-8") as f:
        f.write(log_entry)


async def update_summary(
    platform: str,
    message: str,
    post_id: str,
    status: str
) -> None:
    """Update social_summary.md with post information."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat()

    entry = f"""
---

### {platform.upper()} Post

| Field | Value |
|-------|-------|
| **Timestamp** | {timestamp} |
| **Post ID** | {post_id} |
| **Status** | {status} |
| **Message** | {message[:100]}{'...' if len(message) > 100 else ''} |

"""

    mode = "a" if SUMMARY_FILE.exists() else "w"
    if mode == "w":
        header = "# Social Media Post Summary\n\nAll published posts are documented here.\n\n"
        entry = header + entry

    with open(SUMMARY_FILE, mode, encoding="utf-8") as f:
        f.write(entry)


# =============================================================================
# Retry Decorator
# =============================================================================

def with_retry(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """Decorator to retry async functions with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = delay * (2 ** (attempt - 1))
                        await asyncio.sleep(wait_time)
                    continue
            raise last_exception
        return wrapper
    return decorator


# =============================================================================
# Approval Workflow
# =============================================================================

def generate_approval_id() -> str:
    """Generate unique approval ID."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"APPROVAL-{timestamp}"


async def create_approval_request(
    approval_id: str,
    platform: str,
    message: str,
    image_url: Optional[str],
    task_ref: str,
    reason: str
) -> Path:
    """Create approval request file in Pending_Approval folder."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    content = f"""# Social Media Post Approval Request

## {approval_id}

| Field | Value |
|-------|-------|
| **Task Reference** | {task_ref} |
| **Platform** | {platform.upper()} |
| **Created** | {datetime.now().isoformat()} |
| **Status** | PENDING APPROVAL |

## Reason for Post

{reason}

## Post Content

```
{message}
```

{"## Image URL" + chr(10) + image_url if image_url else ""}

---

**Instructions:**
- To APPROVE: Move this file to `/Approved/` folder
- To REJECT: Move this file to `/Rejected/` folder

The post will only be published after approval.
"""

    file_path = PENDING_DIR / f"{approval_id}.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


def check_approval_status(approval_id: str) -> ApprovalStatus:
    """Check if approval file exists in Approved, Rejected, or Pending folder."""
    if (APPROVED_DIR / f"{approval_id}.md").exists():
        return ApprovalStatus.APPROVED
    elif (REJECTED_DIR / f"{approval_id}.md").exists():
        return ApprovalStatus.REJECTED
    elif (PENDING_DIR / f"{approval_id}.md").exists():
        return ApprovalStatus.PENDING
    else:
        raise FileNotFoundError(f"Approval {approval_id} not found")


# =============================================================================
# Social Media Clients
# =============================================================================

class FacebookClient:
    """Facebook Graph API client."""

    BASE_URL = "https://graph.facebook.com/v18.0"

    def __init__(self, access_token: str, page_id: str):
        self.access_token = access_token
        self.page_id = page_id

    @with_enhanced_retry(
        service="social_media",
        action="facebook_post_message",
        config=RetryConfig(max_retries=MAX_RETRIES),
        timeout_config=TIMEOUT_CONFIG
    )
    async def post_message(self, message: str) -> dict:
        """Post text message to Facebook page."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/{self.page_id}/feed",
                data={
                    "message": message,
                    "access_token": self.access_token
                }
            )
            response.raise_for_status()
            return response.json()

    @with_enhanced_retry(
        service="social_media",
        action="facebook_post_photo",
        config=RetryConfig(max_retries=MAX_RETRIES),
        timeout_config=TIMEOUT_CONFIG
    )
    async def post_photo(self, message: str, image_url: str) -> dict:
        """Post photo with caption to Facebook page."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/{self.page_id}/photos",
                data={
                    "url": image_url,
                    "caption": message,
                    "access_token": self.access_token
                }
            )
            response.raise_for_status()
            return response.json()


class InstagramClient:
    """Instagram Graph API client."""

    BASE_URL = "https://graph.facebook.com/v18.0"

    def __init__(self, access_token: str, business_id: str):
        self.access_token = access_token
        self.business_id = business_id

    @with_enhanced_retry(
        service="social_media",
        action="instagram_create_media",
        config=RetryConfig(max_retries=MAX_RETRIES),
        timeout_config=TIMEOUT_CONFIG
    )
    async def create_media_container(self, image_url: str, caption: str) -> str:
        """Create media container for Instagram post."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/{self.business_id}/media",
                data={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": self.access_token
                }
            )
            response.raise_for_status()
            return response.json()["id"]

    @with_enhanced_retry(
        service="social_media",
        action="instagram_publish_media",
        config=RetryConfig(max_retries=MAX_RETRIES),
        timeout_config=TIMEOUT_CONFIG
    )
    async def publish_media(self, container_id: str) -> dict:
        """Publish media container to Instagram."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/{self.business_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": self.access_token
                }
            )
            response.raise_for_status()
            return response.json()


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "MCP Social Media Publisher",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.post("/draft-post", response_model=PostResponse)
async def draft_post(request: CreatePostRequest):
    """
    Create a social media post draft and request approval.

    Does NOT publish immediately. Creates approval request in Pending_Approval folder.
    The Vault Owner must move the file to /Approved/ before publishing.
    """
    action = f"Draft {request.platform.value.upper()} Post"
    details = request.model_dump()

    # Log to universal audit logger
    audit_logger.info(
        f"Creating {request.platform.value} post draft",
        action=ActionType.APPROVAL_REQUESTED,
        details={"platform": request.platform.value, "task_ref": request.task_ref}
    )

    try:
        approval_id = generate_approval_id()

        # Create approval request file
        await create_approval_request(
            approval_id=approval_id,
            platform=request.platform.value,
            message=request.message,
            image_url=request.image_url,
            task_ref=request.task_ref,
            reason=request.reason
        )

        await log_action(
            action=action,
            status="PENDING_APPROVAL",
            details={**details, "approval_id": approval_id}
        )

        return PostResponse(
            success=True,
            message=f"Post draft created. Awaiting approval at Pending_Approval/{approval_id}.md",
            approval_id=approval_id,
            data={"platform": request.platform.value, "status": "pending_approval"}
        )

    except Exception as e:
        error_msg = str(e)

        await log_action(
            action=action,
            status="FAILED",
            details=details,
            error=error_msg
        )

        return PostResponse(
            success=False,
            message=f"Failed to create post draft: {error_msg}"
        )


@app.post("/publish-post", response_model=PostResponse)
async def publish_post(request: PublishRequest):
    """
    Publish an approved social media post.

    Requires APPROVAL-XXX.md to exist in /Approved/ folder.
    Blocked if file is still in Pending_Approval/ or Rejected/.
    """
    action = "Publish Post"
    approval_id = request.approval_id

    try:
        # Check approval status
        status = check_approval_status(approval_id)

        if status == ApprovalStatus.PENDING:
            return PostResponse(
                success=False,
                message=f"Post {approval_id} is still pending approval. Move to /Approved/ to publish.",
                approval_id=approval_id
            )

        if status == ApprovalStatus.REJECTED:
            return PostResponse(
                success=False,
                message=f"Post {approval_id} was rejected and cannot be published.",
                approval_id=approval_id
            )

        # Read approval file to get post details
        approval_file = APPROVED_DIR / f"{approval_id}.md"
        content = approval_file.read_text(encoding="utf-8")

        # Parse platform and message from approval file
        platform = "facebook" if "FACEBOOK" in content else "instagram"

        # Extract message from code block
        import re
        message_match = re.search(r"```\n(.+?)\n```", content, re.DOTALL)
        message = message_match.group(1) if message_match else ""

        # Extract image URL if present
        image_match = re.search(r"## Image URL\n(.+?)(?:\n|$)", content)
        image_url = image_match.group(1).strip() if image_match else None

        # Publish based on platform
        if platform == "facebook":
            if not FB_ACCESS_TOKEN or not FB_PAGE_ID:
                raise ValueError("Facebook credentials not configured")

            client = FacebookClient(FB_ACCESS_TOKEN, FB_PAGE_ID)

            if image_url:
                result = await client.post_photo(message, image_url)
            else:
                result = await client.post_message(message)

            post_id = result.get("id", "unknown")

        else:  # Instagram
            if not FB_ACCESS_TOKEN or not IG_BUSINESS_ID:
                raise ValueError("Instagram credentials not configured")

            if not image_url:
                raise ValueError("Instagram requires an image URL")

            client = InstagramClient(FB_ACCESS_TOKEN, IG_BUSINESS_ID)
            container_id = await client.create_media_container(image_url, message)
            result = await client.publish_media(container_id)
            post_id = result.get("id", "unknown")

        # Update summary
        await update_summary(platform, message, post_id, "PUBLISHED")

        await log_action(
            action=action,
            status="SUCCESS",
            details={
                "approval_id": approval_id,
                "platform": platform,
                "post_id": post_id
            }
        )

        # Log to universal audit logger
        audit_logger.success(
            f"Post published to {platform.upper()}: {post_id}",
            action=ActionType.API_RESPONSE,
            details={"approval_id": approval_id, "platform": platform, "post_id": post_id}
        )

        return PostResponse(
            success=True,
            message=f"Post published successfully to {platform.upper()}",
            approval_id=approval_id,
            post_id=post_id,
            data={"platform": platform, "result": result}
        )

    except FileNotFoundError:
        return PostResponse(
            success=False,
            message=f"Approval {approval_id} not found in any folder",
            approval_id=approval_id
        )

    except Exception as e:
        error_msg = str(e)

        await log_action(
            action=action,
            status="FAILED",
            details={"approval_id": approval_id},
            error=error_msg
        )

        # Use enhanced error handler - save to Needs_Action for retry
        error_result = error_handler.handle(
            error=e,
            action=action,
            approval_id=approval_id,
            request_data={"approval_id": approval_id},
            save_for_retry=True
        )

        return PostResponse(
            success=False,
            message=f"Failed to publish: {error_msg}. Task saved for retry.",
            approval_id=approval_id,
            data={"retry_file": error_result.needs_action_file}
        )


@app.get("/pending-approvals")
async def list_pending_approvals():
    """List all posts pending approval."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    pending = []
    for file in PENDING_DIR.glob("APPROVAL-*.md"):
        pending.append({
            "approval_id": file.stem,
            "file": str(file),
            "created": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
        })

    return {
        "pending_count": len(pending),
        "approvals": sorted(pending, key=lambda x: x["created"], reverse=True)
    }


@app.get("/post-summary", response_model=PostSummary)
async def get_post_summary():
    """Get summary of all social media posts."""

    # Count pending approvals
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    pending_count = len(list(PENDING_DIR.glob("APPROVAL-*.md")))

    # Parse summary file for stats
    facebook_count = 0
    instagram_count = 0
    recent_posts = []

    if SUMMARY_FILE.exists():
        content = SUMMARY_FILE.read_text(encoding="utf-8")
        facebook_count = content.count("FACEBOOK Post")
        instagram_count = content.count("INSTAGRAM Post")

    return PostSummary(
        success=True,
        total_posts=facebook_count + instagram_count,
        facebook_posts=facebook_count,
        instagram_posts=instagram_count,
        pending_approvals=pending_count,
        recent_posts=recent_posts
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "MCP Social Media Publisher",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "facebook_configured": bool(FB_ACCESS_TOKEN and FB_PAGE_ID),
        "instagram_configured": bool(FB_ACCESS_TOKEN and IG_BUSINESS_ID)
    }


# =============================================================================
# Startup Event
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize directories on startup."""
    for dir_path in [REPORTS_DIR, PENDING_DIR, APPROVED_DIR, REJECTED_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)

    await log_action(
        action="Server Startup",
        status="INFO",
        details={"message": "MCP Social Media Publisher started"}
    )


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
