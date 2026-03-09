# Gold Tier Autonomous Employee - System Architecture

**Version:** 1.0.0
**Last Updated:** 2026-03-09
**Status:** Production Ready

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Folder Structure](#2-folder-structure)
3. [Data Flow Diagram](#3-data-flow-diagram)
4. [MCP Server Architecture](#4-mcp-server-architecture)
5. [Error Handling Strategy](#5-error-handling-strategy)
6. [Security Design](#6-security-design)
7. [Lessons Learned](#7-lessons-learned)
8. [Future Improvements](#8-future-improvements)

---

## 1. System Overview

### 1.1 Purpose

The Gold Tier Autonomous Employee is an AI-powered autonomous agent system designed to handle enterprise operations including:

- **Financial Operations** - Invoice creation, expense tracking via Odoo ERP
- **Social Media Management** - Facebook, Instagram, X (Twitter) publishing
- **Executive Reporting** - Automated CEO weekly briefings
- **Task Orchestration** - Autonomous task processing with human-in-the-loop approval

### 1.2 Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Human-in-the-Loop** | All external actions require explicit approval via file-based workflow |
| **Audit Compliance** | Every action is logged with timestamps, sources, and outcomes |
| **Fault Tolerance** | 3-retry policy with exponential backoff; failed tasks auto-recover |
| **Separation of Concerns** | Modular MCP servers for each integration domain |
| **Transparency** | Markdown-based logs readable by humans and machines |

### 1.3 Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    GOLD TIER AUTONOMOUS EMPLOYEE                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ RALPH Loop  │───▶│   Skills    │───▶│   Reports   │         │
│  │  (Core)     │    │  (Actions)  │    │  (Output)   │         │
│  └──────┬──────┘    └─────────────┘    └─────────────┘         │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              MCP Server Layer                        │       │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐             │       │
│  │  │  Odoo   │  │ Social  │  │    X    │             │       │
│  │  │ :8001   │  │ :8002   │  │  :8003  │             │       │
│  │  └─────────┘  └─────────┘  └─────────┘             │       │
│  └─────────────────────────────────────────────────────┘       │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────────────────────────────────────────────┐       │
│  │           Shared Infrastructure                      │       │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │       │
│  │  │   Logger    │  │   Error     │  │  Approval   │ │       │
│  │  │  (Audit)    │  │  Handler    │  │  Workflow   │ │       │
│  │  └─────────────┘  └─────────────┘  └─────────────┘ │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Folder Structure

```
Gold Tier/
│
├── core/                          # Core automation engine
│   ├── ralph_loop.py              # Main autonomous loop controller
│   ├── logger.py                  # Universal audit logging system
│   └── skills/                    # Agent skills (actions)
│       └── weekly_ceo_briefing.py # CEO report generation skill
│
├── mcp_servers/                   # MCP (Model Context Protocol) servers
│   ├── mcp_odoo_server.py         # Odoo ERP integration (port 8001)
│   ├── mcp_social_media_server.py # Facebook/Instagram (port 8002)
│   ├── mcp_x_publisher.py         # X/Twitter integration (port 8003)
│   └── error_handler.py           # Shared error handling utilities
│
├── Needs_Action/                  # Tasks requiring processing
│   └── *.md                       # Task files (parsed by RALPH)
│
├── Pending_Approval/              # Items awaiting human approval
│   └── APPROVAL-*.md              # Approval request files
│
├── Approved/                      # Human-approved items
│   └── APPROVAL-*.md              # Ready for execution
│
├── Rejected/                      # Human-rejected items
│   └── APPROVAL-*.md              # Will not be executed
│
├── Reports/                       # Generated reports
│   ├── CEO_Weekly_Briefing.md     # Executive summary
│   ├── ralph_summary_*.md         # RALPH execution summaries
│   ├── social_summary.md          # Social media post log
│   └── x_analytics_weekly.md      # X engagement metrics
│
├── Logs/                          # Audit and debug logs
│   ├── master_audit.md            # Universal audit trail
│   ├── audit.json                 # Machine-readable logs
│   ├── errors.md                  # Dedicated error log
│   ├── ralph_loop.md              # RALPH execution log
│   ├── odoo_log.md                # Odoo transaction log
│   ├── social_log.md              # Social media action log
│   └── error_fallback.md          # Fallback error capture
│
├── .env                           # Environment variables (secrets)
├── Company_Handbook.md            # Business context for AI
└── ARCHITECTURE.md                # This document
```

### 2.1 Folder Purposes

| Folder | Purpose | Lifecycle |
|--------|---------|-----------|
| `Needs_Action/` | Input queue for tasks | Created → Processed → Deleted |
| `Pending_Approval/` | Human review queue | Created by system → Moved by human |
| `Approved/` | Execution queue | Moved here by human → Executed → Archived |
| `Rejected/` | Rejection archive | Moved here by human → Retained for audit |
| `Reports/` | Output artifacts | Generated → Retained indefinitely |
| `Logs/` | Audit trail | Appended → Rotated at 10MB |

---

## 3. Data Flow Diagram

### 3.1 Task Processing Flow

```
                                    TASK LIFECYCLE
═══════════════════════════════════════════════════════════════════════════

     ┌──────────────┐
     │  External    │
     │  Trigger     │
     │ (User/Cron)  │
     └──────┬───────┘
            │
            ▼
┌───────────────────────┐
│    /Needs_Action/     │◀────────────────────────────────┐
│    task_001.md        │                                  │
└───────────┬───────────┘                                  │
            │                                              │
            ▼                                              │
┌───────────────────────┐                                  │
│     RALPH Loop        │                                  │
│  ┌─────────────────┐  │                                  │
│  │ 1. Scan         │  │                                  │
│  │ 2. Reason       │  │                                  │
│  │ 3. Check Deps   │  │                                  │
│  │ 4. Execute      │  │                                  │
│  │ 5. Handle Err   │  │                                  │
│  │ 6. Re-evaluate  │  │                                  │
│  └─────────────────┘  │                                  │
└───────────┬───────────┘                                  │
            │                                              │
            ▼                                              │
┌───────────────────────┐         ┌────────────────┐       │
│   MCP Server Call     │────────▶│  External API  │       │
│   (Odoo/Social/X)     │◀────────│  (Success)     │       │
└───────────┬───────────┘         └────────────────┘       │
            │                              │               │
            │                              ▼               │
            │                     ┌────────────────┐       │
            │                     │  External API  │       │
            │                     │  (Failure)     │       │
            │                     └───────┬────────┘       │
            │                             │                │
            │                             ▼                │
            │                     ┌────────────────┐       │
            │                     │ Error Handler  │───────┘
            │                     │ (Retry/Save)   │ Save to Needs_Action
            │                     └────────────────┘
            ▼
┌───────────────────────┐
│  /Pending_Approval/   │
│  APPROVAL-X-001.md    │
└───────────┬───────────┘
            │
            │ Human moves file
            ▼
    ┌───────┴───────┐
    │               │
    ▼               ▼
┌────────┐    ┌──────────┐
│Approved│    │ Rejected │
│ Folder │    │  Folder  │
└───┬────┘    └──────────┘
    │
    │ RALPH detects
    ▼
┌───────────────────────┐
│   Execute Approved    │
│   (Publish/Send)      │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│      /Reports/        │
│   + /Logs/ updated    │
└───────────────────────┘
```

### 3.2 Approval Workflow Detail

```
┌─────────────────────────────────────────────────────────────────┐
│                     APPROVAL WORKFLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Agent Action                    Human Action                  │
│   ────────────                    ────────────                  │
│                                                                 │
│   1. Generate content                                           │
│          │                                                      │
│          ▼                                                      │
│   2. Create APPROVAL-*.md ──────▶ 3. Review content             │
│      in /Pending_Approval/              │                       │
│                                         │                       │
│                                         ▼                       │
│                                  4. Decision:                   │
│                                     │                           │
│                           ┌─────────┴─────────┐                 │
│                           │                   │                 │
│                           ▼                   ▼                 │
│                    Move to /Approved/   Move to /Rejected/      │
│                           │                   │                 │
│                           ▼                   ▼                 │
│   5. Detect & Execute ◀───┘                   │                 │
│          │                                    │                 │
│          ▼                                    │                 │
│   6. Log result                        Log rejection            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. MCP Server Architecture

### 4.1 Server Overview

| Server | Port | Purpose | External APIs |
|--------|------|---------|---------------|
| `mcp_odoo_server.py` | 8001 | ERP operations | Odoo JSON-RPC |
| `mcp_social_media_server.py` | 8002 | Social publishing | Facebook/Instagram Graph API |
| `mcp_x_publisher.py` | 8003 | X/Twitter posting | X API v2 (Tweepy) |

### 4.2 Server Structure

Each MCP server follows a consistent architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                      MCP SERVER TEMPLATE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    FastAPI Application                   │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│  │  │ POST /draft │  │POST /publish│  │ GET /health │      │   │
│  │  └──────┬──────┘  └──────┬──────┘  └─────────────┘      │   │
│  │         │                │                               │   │
│  │         ▼                ▼                               │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │            Business Logic Layer                  │    │   │
│  │  │  • Content generation                           │    │   │
│  │  │  • Approval file creation                       │    │   │
│  │  │  • Status checking                              │    │   │
│  │  └──────────────────────┬──────────────────────────┘    │   │
│  │                         │                               │   │
│  │                         ▼                               │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │              API Client Layer                    │    │   │
│  │  │  • with_enhanced_retry decorator                │    │   │
│  │  │  • Timeout handling                             │    │   │
│  │  │  • Response parsing                             │    │   │
│  │  └──────────────────────┬──────────────────────────┘    │   │
│  │                         │                               │   │
│  │                         ▼                               │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │           Shared Infrastructure                  │    │   │
│  │  │  ┌───────────┐ ┌───────────┐ ┌───────────┐      │    │   │
│  │  │  │  Logger   │ │  Error    │ │  Audit    │      │    │   │
│  │  │  │           │ │  Handler  │ │  Trail    │      │    │   │
│  │  │  └───────────┘ └───────────┘ └───────────┘      │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 API Endpoints Reference

#### Odoo Server (Port 8001)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/create-invoice` | Create customer/vendor invoice |
| POST | `/create-expense` | Create expense record |
| GET | `/weekly-financial-summary` | Get 7-day financial metrics |
| GET | `/health` | Health check |

#### Social Media Server (Port 8002)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/draft-post` | Create post draft for approval |
| POST | `/publish-post` | Publish approved post |
| GET | `/pending-approvals` | List pending items |
| GET | `/post-summary` | Get posting statistics |
| GET | `/health` | Health check |

#### X Publisher Server (Port 8003)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/generate-tweet` | AI-generate tweet content |
| POST | `/draft-tweet` | Create tweet draft for approval |
| POST | `/publish-tweet` | Publish approved tweet |
| GET | `/pending-approvals` | List pending items |
| GET | `/weekly-analytics` | Get engagement metrics |
| POST | `/save-weekly-summary` | Save analytics report |
| GET | `/health` | Health check |

---

## 5. Error Handling Strategy

### 5.1 Error Handling Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                    ERROR HANDLING LAYERS                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 1: Retry Decorator                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  @with_enhanced_retry(max_retries=3)                    │   │
│  │  • Exponential backoff: 1s → 2s → 4s                    │   │
│  │  • Jitter to prevent thundering herd                    │   │
│  │  • Configurable timeout (default: 30s)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼ If all retries fail                   │
│  Layer 2: Error Classification                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ErrorClassifier.classify(exception)                    │   │
│  │  • NETWORK    → Retryable    (MEDIUM severity)          │   │
│  │  • TIMEOUT    → Retryable    (MEDIUM severity)          │   │
│  │  • RATE_LIMIT → Retryable    (LOW severity)             │   │
│  │  • AUTH       → Not Retry    (HIGH severity)            │   │
│  │  • VALIDATION → Not Retry    (LOW severity)             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  Layer 3: Fallback Logging                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  FallbackLogger.log()                                   │   │
│  │  • Write to /Logs/error_fallback.md                     │   │
│  │  • Include full stack trace                             │   │
│  │  • Capture request context                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  Layer 4: Task Recovery                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  NeedsActionRecovery.save_for_retry()                   │   │
│  │  • Create RETRY-{SERVICE}-{TIMESTAMP}.md                │   │
│  │  • Save to /Needs_Action/                               │   │
│  │  • Mark as "Retry Required"                             │   │
│  │  • RALPH loop auto-picks up on next iteration           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  Layer 5: Audit Logging                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  AuditLogger.error()                                    │   │
│  │  • Log to /Logs/master_audit.md                         │   │
│  │  • Log to /Logs/audit.json                              │   │
│  │  • Log to /Logs/errors.md                               │   │
│  │  • Console output with color coding                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Retry Configuration

```python
RetryConfig(
    max_retries=3,           # Maximum attempts
    base_delay=1.0,          # Initial delay (seconds)
    max_delay=30.0,          # Maximum delay cap
    exponential_base=2.0,    # Backoff multiplier
    jitter=True              # Add randomness
)

TimeoutConfig(
    connect_timeout=10.0,    # Connection establishment
    read_timeout=30.0,       # Response reading
    total_timeout=60.0       # Overall operation
)
```

### 5.3 Error Categories

| Category | Retryable | Severity | Example |
|----------|-----------|----------|---------|
| NETWORK | Yes | MEDIUM | Connection refused, DNS failure |
| TIMEOUT | Yes | MEDIUM | Read timeout, connect timeout |
| RATE_LIMIT | Yes | LOW | 429 Too Many Requests |
| API | Yes | MEDIUM | 500 Internal Server Error |
| AUTHENTICATION | No | HIGH | 401 Unauthorized, invalid token |
| VALIDATION | No | LOW | 400 Bad Request, missing field |

---

## 6. Security Design

### 6.1 Security Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      SECURITY LAYERS                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 1: Credential Management                         │   │
│  │  • All secrets in .env file (git-ignored)              │   │
│  │  • Environment variable injection at runtime            │   │
│  │  • No hardcoded credentials in code                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 2: Human-in-the-Loop Approval                    │   │
│  │  • ALL external actions require human approval          │   │
│  │  • File-based workflow (move to /Approved/)            │   │
│  │  • No automatic execution of sensitive operations       │   │
│  │  • Full content preview before approval                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 3: Audit Trail                                   │   │
│  │  • Every action logged with timestamp                   │   │
│  │  • Source attribution (which service/skill)            │   │
│  │  • Request/response data captured                       │   │
│  │  • Immutable append-only logs                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 4: Input Validation                              │   │
│  │  • Pydantic models for all API inputs                   │   │
│  │  • Type checking and constraints                        │   │
│  │  • Sanitization of user-provided content                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 5: Network Security                              │   │
│  │  • MCP servers bind to localhost by default            │   │
│  │  • HTTPS for all external API calls                     │   │
│  │  • Timeout limits prevent hanging connections           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Credential Requirements

| Service | Required Environment Variables |
|---------|-------------------------------|
| Odoo | `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_PASSWORD` |
| Facebook | `FB_ACCESS_TOKEN`, `FB_PAGE_ID` |
| Instagram | `FB_ACCESS_TOKEN`, `IG_BUSINESS_ID` |
| X (Twitter) | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`, `X_BEARER_TOKEN` |

### 6.3 Approval File Security

Approval files contain:
- Full content to be published
- Task reference for traceability
- Reason/justification
- Clear instructions for human reviewer

```markdown
# X (Twitter) Post Approval Request

## APPROVAL-X-20260309120000

| Field | Value |
|-------|-------|
| **Task Reference** | TASK-001 |
| **Platform** | X (Twitter) |
| **Status** | PENDING APPROVAL |

## Tweet Content

```
[Full content visible for review]
```

**Instructions:**
- To APPROVE: Move this file to `/Approved/` folder
- To REJECT: Move this file to `/Rejected/` folder
```

---

## 7. Lessons Learned

### 7.1 Design Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| **File-based approval workflow** | Simple, auditable, no database required | Works well for low-volume, high-stakes operations |
| **Markdown for logs** | Human-readable, version-control friendly | Easy to review and debug |
| **Singleton logger pattern** | Consistent logging across services | Simplified integration |
| **Exponential backoff** | Prevents overwhelming failing services | Improved reliability |
| **Task recovery to Needs_Action** | Self-healing system | Reduced manual intervention |

### 7.2 Challenges Addressed

| Challenge | Solution |
|-----------|----------|
| API rate limits | Retry with exponential backoff + jitter |
| Lost tasks on failure | Automatic save to `/Needs_Action/` for retry |
| Audit compliance | Multi-layer logging (console, markdown, JSON) |
| Human oversight | Mandatory approval workflow for all external actions |
| Error diagnosis | Full stack traces in error logs |
| Cross-service logging | Universal `AuditLogger` shared by all services |

### 7.3 What Worked Well

1. **Separation of concerns** - Each MCP server handles one domain
2. **Standardized error handling** - Shared `error_handler.py` reduces duplication
3. **Skill-based architecture** - New capabilities added as skills
4. **RALPH loop pattern** - Simple, effective autonomous task processing

### 7.4 What Could Be Improved

1. **Database integration** - File-based system doesn't scale to high volume
2. **Real-time monitoring** - Add WebSocket dashboard for live status
3. **Unit test coverage** - Current testing is manual
4. **Containerization** - Docker setup for easier deployment

---

## 8. Future Improvements

### 8.1 Short-Term (1-3 months)

| Improvement | Priority | Effort |
|-------------|----------|--------|
| Add email MCP server | High | Medium |
| Implement webhook notifications | Medium | Low |
| Add Slack integration | Medium | Medium |
| Unit test suite | High | High |
| Docker containerization | Medium | Low |

### 8.2 Medium-Term (3-6 months)

| Improvement | Priority | Effort |
|-------------|----------|--------|
| Web dashboard for approvals | High | High |
| PostgreSQL for task storage | Medium | Medium |
| Multi-tenant support | Low | High |
| AI-powered task prioritization | Medium | Medium |
| Scheduled task support (cron) | High | Low |

### 8.3 Long-Term (6-12 months)

| Improvement | Priority | Effort |
|-------------|----------|--------|
| Kubernetes deployment | Low | High |
| Plugin marketplace for skills | Low | Very High |
| Natural language task creation | Medium | High |
| Cross-organization workflows | Low | Very High |
| Compliance certifications (SOC2) | Medium | Very High |

### 8.4 Architecture Evolution

```
CURRENT STATE                        FUTURE STATE
═════════════                        ════════════

┌──────────────┐                    ┌──────────────┐
│  File-based  │                    │  PostgreSQL  │
│   Storage    │        ───▶        │   Database   │
└──────────────┘                    └──────────────┘

┌──────────────┐                    ┌──────────────┐
│   Manual     │                    │     Web      │
│  Approvals   │        ───▶        │  Dashboard   │
└──────────────┘                    └──────────────┘

┌──────────────┐                    ┌──────────────┐
│   Console    │                    │   Grafana    │
│   Logging    │        ───▶        │  Dashboards  │
└──────────────┘                    └──────────────┘

┌──────────────┐                    ┌──────────────┐
│   Manual     │                    │  Kubernetes  │
│  Deployment  │        ───▶        │   + Helm     │
└──────────────┘                    └──────────────┘
```

---

## Appendix A: Quick Reference

### Starting the System

```bash
# Terminal 1: Odoo Server
cd mcp_servers
python mcp_odoo_server.py

# Terminal 2: Social Media Server
python mcp_social_media_server.py

# Terminal 3: X Publisher Server
python mcp_x_publisher.py

# Terminal 4: RALPH Loop
cd ../core
python ralph_loop.py
```

### Environment Variables Template

```env
# Odoo Configuration
ODOO_URL=https://your-odoo.com
ODOO_DB=your_database
ODOO_USERNAME=admin
ODOO_PASSWORD=your_password

# Facebook/Instagram
FB_ACCESS_TOKEN=your_token
FB_PAGE_ID=your_page_id
IG_BUSINESS_ID=your_ig_id

# X (Twitter)
X_API_KEY=your_key
X_API_SECRET=your_secret
X_ACCESS_TOKEN=your_token
X_ACCESS_TOKEN_SECRET=your_token_secret
X_BEARER_TOKEN=your_bearer

# Company
COMPANY_NAME=Your Company
```

### Health Check URLs

- Odoo: http://localhost:8001/health
- Social: http://localhost:8002/health
- X: http://localhost:8003/health

---

*Documentation generated for Gold Tier Autonomous Employee v1.0.0*
*Last updated: 2026-03-09*
