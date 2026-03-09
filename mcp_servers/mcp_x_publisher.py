"""
MCP X Publisher - Gold Tier Autonomous Employee
FastAPI server for X (Twitter) posting via Tweepy with approval workflow
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
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
audit_logger = get_logger(ServiceSource.X_PUBLISHER)

# =============================================================================
# Configuration
# =============================================================================

X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")

MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "Reports"
PENDING_DIR = BASE_DIR / "Pending_Approval"
APPROVED_DIR = BASE_DIR / "Approved"
REJECTED_DIR = BASE_DIR / "Rejected"
LOG_FILE = BASE_DIR / "Logs" / "social_log.md"
ANALYTICS_FILE = REPORTS_DIR / "x_analytics_weekly.md"

# Initialize error handler
error_handler = MCPErrorHandler("x_publisher")

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
    title="MCP X Publisher",
    description="Gold Tier Autonomous Employee - X (Twitter) Integration with Approval Workflow",
    version="1.0.0"
)

# =============================================================================
# Enums
# =============================================================================

class TweetType(str, Enum):
    STANDARD = "standard"
    THREAD = "thread"
    QUOTE = "quote"
    REPLY = "reply"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# =============================================================================
# Pydantic Models
# =============================================================================

class GenerateTweetRequest(BaseModel):
    topic: str = Field(..., description="Business topic for tweet generation")
    tone: str = Field(default="professional", description="Tone: professional, casual, engaging, informative")
    include_hashtags: bool = Field(default=True, description="Include relevant hashtags")
    include_cta: bool = Field(default=False, description="Include call-to-action")
    max_length: int = Field(default=280, le=280, description="Maximum tweet length")


class CreateTweetRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=280, description="Tweet content")
    tweet_type: TweetType = Field(default=TweetType.STANDARD, description="Type of tweet")
    media_urls: Optional[list[str]] = Field(default=None, description="Media URLs to attach")
    reply_to_id: Optional[str] = Field(default=None, description="Tweet ID to reply to")
    quote_tweet_id: Optional[str] = Field(default=None, description="Tweet ID to quote")
    task_ref: str = Field(..., description="TASK-XXX reference for tracking")
    reason: str = Field(..., description="Why this tweet is being posted")


class TweetResponse(BaseModel):
    success: bool
    message: str
    approval_id: Optional[str] = None
    tweet_id: Optional[str] = None
    data: Optional[dict] = None


class PublishRequest(BaseModel):
    approval_id: str = Field(..., description="APPROVAL-XXX from approved folder")


class AnalyticsSummary(BaseModel):
    success: bool
    period_start: str
    period_end: str
    total_tweets: int
    total_impressions: int
    total_engagements: int
    top_performing_tweets: list[dict]


class GeneratedTweet(BaseModel):
    success: bool
    content: str
    hashtags: list[str]
    character_count: int
    suggestions: list[str]


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

## [X Publisher] {action}

| Field | Value |
|-------|-------|
| **Timestamp** | {timestamp} |
| **Status** | {status} |
| **Platform** | X (Twitter) |
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


async def update_analytics(
    tweet_id: str,
    content: str,
    impressions: int = 0,
    engagements: int = 0
) -> None:
    """Update weekly analytics file."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat()
    week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
    week_end = (datetime.now() + timedelta(days=6 - datetime.now().weekday())).strftime("%Y-%m-%d")

    entry = f"""
---

### Tweet Published

| Field | Value |
|-------|-------|
| **Tweet ID** | {tweet_id} |
| **Timestamp** | {timestamp} |
| **Week** | {week_start} to {week_end} |
| **Content** | {content[:100]}{'...' if len(content) > 100 else ''} |
| **Impressions** | {impressions} |
| **Engagements** | {engagements} |

"""

    mode = "a" if ANALYTICS_FILE.exists() else "w"
    if mode == "w":
        header = f"""# X (Twitter) Weekly Analytics

**Report Period:** {week_start} to {week_end}

All X posts and their performance metrics are documented here.

"""
        entry = header + entry

    with open(ANALYTICS_FILE, mode, encoding="utf-8") as f:
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
    return f"APPROVAL-X-{timestamp}"


async def create_approval_request(
    approval_id: str,
    content: str,
    tweet_type: str,
    media_urls: Optional[list[str]],
    task_ref: str,
    reason: str,
    reply_to_id: Optional[str] = None,
    quote_tweet_id: Optional[str] = None
) -> Path:
    """Create approval request file in Pending_Approval folder."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    media_section = ""
    if media_urls:
        media_section = "\n## Media URLs\n" + "\n".join(f"- {url}" for url in media_urls)

    reply_section = f"\n| **Reply To** | {reply_to_id} |" if reply_to_id else ""
    quote_section = f"\n| **Quote Tweet** | {quote_tweet_id} |" if quote_tweet_id else ""

    content_text = f"""# X (Twitter) Post Approval Request

## {approval_id}

| Field | Value |
|-------|-------|
| **Task Reference** | {task_ref} |
| **Platform** | X (Twitter) |
| **Tweet Type** | {tweet_type.upper()} |
| **Character Count** | {len(content)}/280 |
| **Created** | {datetime.now().isoformat()} |
| **Status** | PENDING APPROVAL |{reply_section}{quote_section}

## Reason for Post

{reason}

## Tweet Content

```
{content}
```
{media_section}

---

**Instructions:**
- To APPROVE: Move this file to `/Approved/` folder
- To REJECT: Move this file to `/Rejected/` folder

The tweet will only be published after approval.
"""

    file_path = PENDING_DIR / f"{approval_id}.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content_text)

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
# X (Twitter) Client via Tweepy
# =============================================================================

class XClient:
    """X (Twitter) API client using Tweepy."""

    def __init__(self):
        self.api_key = X_API_KEY
        self.api_secret = X_API_SECRET
        self.access_token = X_ACCESS_TOKEN
        self.access_token_secret = X_ACCESS_TOKEN_SECRET
        self.bearer_token = X_BEARER_TOKEN
        self._client = None

    def _get_client(self):
        """Initialize Tweepy client lazily."""
        if self._client is None:
            try:
                import tweepy
                self._client = tweepy.Client(
                    bearer_token=self.bearer_token,
                    consumer_key=self.api_key,
                    consumer_secret=self.api_secret,
                    access_token=self.access_token,
                    access_token_secret=self.access_token_secret
                )
            except ImportError:
                raise ImportError("Tweepy is not installed. Run: pip install tweepy")
        return self._client

    @with_enhanced_retry(
        service="x_publisher",
        action="post_tweet",
        config=RetryConfig(max_retries=MAX_RETRIES),
        timeout_config=TIMEOUT_CONFIG
    )
    async def post_tweet(
        self,
        text: str,
        reply_to_id: Optional[str] = None,
        quote_tweet_id: Optional[str] = None
    ) -> dict:
        """Post a tweet to X."""
        client = self._get_client()

        kwargs = {"text": text}
        if reply_to_id:
            kwargs["in_reply_to_tweet_id"] = reply_to_id
        if quote_tweet_id:
            kwargs["quote_tweet_id"] = quote_tweet_id

        # Run in executor since tweepy is synchronous
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.create_tweet(**kwargs)
        )

        return {
            "id": str(response.data["id"]),
            "text": response.data["text"]
        }

    @with_enhanced_retry(
        service="x_publisher",
        action="get_tweet_metrics",
        config=RetryConfig(max_retries=MAX_RETRIES),
        timeout_config=TIMEOUT_CONFIG
    )
    async def get_tweet_metrics(self, tweet_id: str) -> dict:
        """Get engagement metrics for a tweet."""
        client = self._get_client()

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.get_tweet(
                tweet_id,
                tweet_fields=["public_metrics"]
            )
        )

        metrics = response.data.get("public_metrics", {})
        return {
            "impressions": metrics.get("impression_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "likes": metrics.get("like_count", 0),
            "replies": metrics.get("reply_count", 0),
            "quotes": metrics.get("quote_count", 0)
        }


# =============================================================================
# Business Tweet Generator
# =============================================================================

class TweetGenerator:
    """Generate business-focused tweets."""

    TEMPLATES = {
        "professional": [
            "📊 {topic} - Here's what you need to know: {insight}",
            "💼 {topic}: A key insight for business leaders. {insight}",
            "🎯 {topic} update: {insight} #Business #Growth"
        ],
        "casual": [
            "Quick thought on {topic} 💡 {insight}",
            "Been thinking about {topic}... {insight} 🤔",
            "{topic} is changing the game! {insight} 🚀"
        ],
        "engaging": [
            "What's your take on {topic}? 🤔 {insight} Share your thoughts below! 👇",
            "Let's talk about {topic}! {insight} Agree or disagree? 💬",
            "Hot take: {topic} {insight} Change my mind! 🔥"
        ],
        "informative": [
            "Did you know? {topic}: {insight} 📚",
            "THREAD 🧵 on {topic}: {insight}",
            "Key facts about {topic}: {insight} 📈"
        ]
    }

    BUSINESS_HASHTAGS = [
        "#Business", "#Entrepreneurship", "#Growth", "#Innovation",
        "#Leadership", "#Strategy", "#Success", "#Startup",
        "#Marketing", "#Technology", "#Industry", "#Trends"
    ]

    CTA_OPTIONS = [
        "Learn more at our website!",
        "DM us for details!",
        "Link in bio!",
        "Follow for more insights!",
        "Share if you agree!"
    ]

    @classmethod
    def generate(
        cls,
        topic: str,
        tone: str = "professional",
        include_hashtags: bool = True,
        include_cta: bool = False,
        max_length: int = 280
    ) -> dict:
        """Generate a business tweet based on parameters."""
        import random

        templates = cls.TEMPLATES.get(tone, cls.TEMPLATES["professional"])
        template = random.choice(templates)

        # Generate insight placeholder (in real implementation, use AI)
        insight = f"Key developments in {topic} are reshaping the industry."

        tweet = template.format(topic=topic, insight=insight)

        # Add hashtags
        hashtags = []
        if include_hashtags:
            topic_hashtag = f"#{topic.replace(' ', '')}"
            hashtags = [topic_hashtag] + random.sample(cls.BUSINESS_HASHTAGS, 2)
            hashtag_str = " ".join(hashtags)

            if len(tweet) + len(hashtag_str) + 1 <= max_length:
                tweet += " " + hashtag_str

        # Add CTA
        if include_cta:
            cta = random.choice(cls.CTA_OPTIONS)
            if len(tweet) + len(cta) + 2 <= max_length:
                tweet += "\n\n" + cta

        # Truncate if needed
        if len(tweet) > max_length:
            tweet = tweet[:max_length - 3] + "..."

        suggestions = [
            "Consider adding relevant media for higher engagement",
            "Best posting times: 9-11 AM or 7-9 PM",
            "Engage with replies within the first hour"
        ]

        return {
            "content": tweet,
            "hashtags": hashtags,
            "character_count": len(tweet),
            "suggestions": suggestions
        }


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "MCP X Publisher",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.post("/generate-tweet", response_model=GeneratedTweet)
async def generate_tweet(request: GenerateTweetRequest):
    """
    Generate a business tweet based on topic and parameters.

    Returns generated content for review before creating draft.
    """
    try:
        result = TweetGenerator.generate(
            topic=request.topic,
            tone=request.tone,
            include_hashtags=request.include_hashtags,
            include_cta=request.include_cta,
            max_length=request.max_length
        )

        await log_action(
            action="Generate Tweet",
            status="SUCCESS",
            details={"topic": request.topic, "tone": request.tone}
        )

        return GeneratedTweet(
            success=True,
            content=result["content"],
            hashtags=result["hashtags"],
            character_count=result["character_count"],
            suggestions=result["suggestions"]
        )

    except Exception as e:
        await log_action(
            action="Generate Tweet",
            status="FAILED",
            details={"topic": request.topic},
            error=str(e)
        )
        return GeneratedTweet(
            success=False,
            content="",
            hashtags=[],
            character_count=0,
            suggestions=[str(e)]
        )


@app.post("/draft-tweet", response_model=TweetResponse)
async def draft_tweet(request: CreateTweetRequest):
    """
    Create a tweet draft and request approval.

    Does NOT publish immediately. Creates approval request in Pending_Approval folder.
    The Vault Owner must move the file to /Approved/ before publishing.
    """
    action = "Draft X Tweet"
    details = request.model_dump()

    # Log to universal audit logger
    audit_logger.info(
        f"Creating X tweet draft",
        action=ActionType.APPROVAL_REQUESTED,
        details={"task_ref": request.task_ref, "tweet_type": request.tweet_type.value}
    )

    try:
        approval_id = generate_approval_id()

        await create_approval_request(
            approval_id=approval_id,
            content=request.content,
            tweet_type=request.tweet_type.value,
            media_urls=request.media_urls,
            task_ref=request.task_ref,
            reason=request.reason,
            reply_to_id=request.reply_to_id,
            quote_tweet_id=request.quote_tweet_id
        )

        await log_action(
            action=action,
            status="PENDING_APPROVAL",
            details={**details, "approval_id": approval_id}
        )

        return TweetResponse(
            success=True,
            message=f"Tweet draft created. Awaiting approval at Pending_Approval/{approval_id}.md",
            approval_id=approval_id,
            data={"tweet_type": request.tweet_type.value, "status": "pending_approval"}
        )

    except Exception as e:
        error_msg = str(e)

        await log_action(
            action=action,
            status="FAILED",
            details=details,
            error=error_msg
        )

        return TweetResponse(
            success=False,
            message=f"Failed to create tweet draft: {error_msg}"
        )


@app.post("/publish-tweet", response_model=TweetResponse)
async def publish_tweet(request: PublishRequest):
    """
    Publish an approved tweet to X.

    Requires APPROVAL-X-XXX.md to exist in /Approved/ folder.
    Blocked if file is still in Pending_Approval/ or Rejected/.
    """
    action = "Publish Tweet"
    approval_id = request.approval_id

    try:
        status = check_approval_status(approval_id)

        if status == ApprovalStatus.PENDING:
            return TweetResponse(
                success=False,
                message=f"Tweet {approval_id} is still pending approval. Move to /Approved/ to publish.",
                approval_id=approval_id
            )

        if status == ApprovalStatus.REJECTED:
            return TweetResponse(
                success=False,
                message=f"Tweet {approval_id} was rejected and cannot be published.",
                approval_id=approval_id
            )

        # Read approval file to get tweet details
        approval_file = APPROVED_DIR / f"{approval_id}.md"
        content = approval_file.read_text(encoding="utf-8")

        # Parse content from code block
        import re
        content_match = re.search(r"```\n(.+?)\n```", content, re.DOTALL)
        tweet_content = content_match.group(1) if content_match else ""

        # Extract reply_to_id if present
        reply_match = re.search(r"\*\*Reply To\*\* \| (\d+)", content)
        reply_to_id = reply_match.group(1) if reply_match else None

        # Extract quote_tweet_id if present
        quote_match = re.search(r"\*\*Quote Tweet\*\* \| (\d+)", content)
        quote_tweet_id = quote_match.group(1) if quote_match else None

        # Check credentials
        if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET]):
            raise ValueError("X API credentials not configured. Set X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET in .env")

        # Publish tweet
        client = XClient()
        result = await client.post_tweet(
            text=tweet_content,
            reply_to_id=reply_to_id,
            quote_tweet_id=quote_tweet_id
        )

        tweet_id = result["id"]

        # Update analytics
        await update_analytics(tweet_id, tweet_content)

        await log_action(
            action=action,
            status="SUCCESS",
            details={
                "approval_id": approval_id,
                "tweet_id": tweet_id
            }
        )

        # Log to universal audit logger
        audit_logger.success(
            f"Tweet published to X: {tweet_id}",
            action=ActionType.API_RESPONSE,
            details={"approval_id": approval_id, "tweet_id": tweet_id}
        )

        return TweetResponse(
            success=True,
            message="Tweet published successfully to X",
            approval_id=approval_id,
            tweet_id=tweet_id,
            data=result
        )

    except FileNotFoundError:
        return TweetResponse(
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

        return TweetResponse(
            success=False,
            message=f"Failed to publish: {error_msg}. Task saved for retry.",
            approval_id=approval_id,
            data={"retry_file": error_result.needs_action_file}
        )


@app.get("/pending-approvals")
async def list_pending_approvals():
    """List all tweets pending approval."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    pending = []
    for file in PENDING_DIR.glob("APPROVAL-X-*.md"):
        pending.append({
            "approval_id": file.stem,
            "file": str(file),
            "created": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
        })

    return {
        "pending_count": len(pending),
        "approvals": sorted(pending, key=lambda x: x["created"], reverse=True)
    }


@app.get("/weekly-analytics", response_model=AnalyticsSummary)
async def get_weekly_analytics():
    """Get weekly analytics summary for X posts."""
    week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
    week_end = (datetime.now() + timedelta(days=6 - datetime.now().weekday())).strftime("%Y-%m-%d")

    total_tweets = 0
    total_impressions = 0
    total_engagements = 0
    top_tweets = []

    if ANALYTICS_FILE.exists():
        content = ANALYTICS_FILE.read_text(encoding="utf-8")
        total_tweets = content.count("### Tweet Published")

        # Parse impressions and engagements
        import re
        impressions = re.findall(r"\*\*Impressions\*\* \| (\d+)", content)
        engagements = re.findall(r"\*\*Engagements\*\* \| (\d+)", content)

        total_impressions = sum(int(i) for i in impressions)
        total_engagements = sum(int(e) for e in engagements)

    return AnalyticsSummary(
        success=True,
        period_start=week_start,
        period_end=week_end,
        total_tweets=total_tweets,
        total_impressions=total_impressions,
        total_engagements=total_engagements,
        top_performing_tweets=top_tweets
    )


@app.post("/save-weekly-summary")
async def save_weekly_summary():
    """Save weekly analytics summary to Reports folder."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
    week_end = (datetime.now() + timedelta(days=6 - datetime.now().weekday())).strftime("%Y-%m-%d")

    analytics = await get_weekly_analytics()

    summary_content = f"""# X (Twitter) Weekly Summary

**Report Generated:** {datetime.now().isoformat()}
**Period:** {week_start} to {week_end}

## Overview

| Metric | Value |
|--------|-------|
| **Total Tweets** | {analytics.total_tweets} |
| **Total Impressions** | {analytics.total_impressions} |
| **Total Engagements** | {analytics.total_engagements} |
| **Avg Engagement Rate** | {(analytics.total_engagements / max(analytics.total_impressions, 1) * 100):.2f}% |

## Recommendations

- Post consistently during peak hours (9-11 AM, 7-9 PM)
- Engage with replies to boost visibility
- Use trending hashtags relevant to your industry
- Include media for higher engagement rates

---

*Generated by MCP X Publisher - Gold Tier Autonomous Employee*
"""

    summary_file = REPORTS_DIR / f"x_weekly_summary_{week_start}.md"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary_content)

    await log_action(
        action="Save Weekly Summary",
        status="SUCCESS",
        details={"file": str(summary_file), "period": f"{week_start} to {week_end}"}
    )

    return {
        "success": True,
        "message": f"Weekly summary saved to {summary_file}",
        "file": str(summary_file)
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "MCP X Publisher",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "x_configured": bool(X_API_KEY and X_API_SECRET and X_ACCESS_TOKEN and X_ACCESS_TOKEN_SECRET)
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
        details={"message": "MCP X Publisher started"}
    )


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
