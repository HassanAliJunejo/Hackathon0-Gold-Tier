# Gold Tier Autonomous Employee

**An Enterprise-Grade AI Agent System for Business Process Automation**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

The **Gold Tier Autonomous Employee** is a production-ready autonomous agent system that handles enterprise operations including financial management, social media publishing, and executive reporting—all with human-in-the-loop approval workflows.

Built for the **Hackathon 0 Gold Tier** challenge, this project demonstrates advanced software architecture patterns, fault-tolerant design, and enterprise security practices.

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUTONOMOUS AGENT SYSTEM                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ RALPH Loop  │───▶│   Skills    │───▶│   Reports   │         │
│  │  (Core)     │    │  (Actions)  │    │  (Output)   │         │
│  └──────┬──────┘    └─────────────┘    └─────────────┘         │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              MCP Server Layer (FastAPI)                  │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐                  │   │
│  │  │  Odoo   │  │ Social  │  │    X    │                  │   │
│  │  │ :8001   │  │ :8002   │  │  :8003  │                  │   │
│  │  └─────────┘  └─────────┘  └─────────┘                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Technical Highlights (The 'Gold' Standard)

### 1. RALPH Loop Architecture

**R**easoning **A**gent **L**oop for **P**rocessing **H**ierarchical Tasks

```python
class RalphLoop:
    """
    Continuously processes tasks until:
    - All tasks are resolved
    - No pending approvals remain
    - Max iterations reached (safety limit)
    """

    async def run(self):
        while not self.state.should_stop:
            # 1. Scan /Needs_Action
            # 2. Run reasoning engine
            # 3. Check dependencies
            # 4. Execute approved tasks
            # 5. Handle errors
            # 6. Re-evaluate system state
```

**Key Features:**
- Autonomous task discovery and execution
- Dependency-aware task ordering
- Self-healing error recovery
- Configurable safety limits (max iterations, consecutive errors)

### 2. Enterprise Error Handling

**5-Layer Error Handling Strategy:**

| Layer | Component | Purpose |
|-------|-----------|---------|
| 1 | `@with_enhanced_retry` | 3 attempts with exponential backoff |
| 2 | `ErrorClassifier` | Categorize errors (network, timeout, auth) |
| 3 | `FallbackLogger` | Capture failures to dedicated log |
| 4 | `NeedsActionRecovery` | Auto-save failed tasks for retry |
| 5 | `AuditLogger` | Universal audit trail |

```python
@with_enhanced_retry(
    service="odoo",
    action="create_invoice",
    config=RetryConfig(max_retries=3, base_delay=1.0),
    timeout_config=TimeoutConfig(total_timeout=60.0)
)
async def create_invoice(data):
    # Automatic retry, timeout, and failure recovery
    ...
```

### 3. Human-in-the-Loop Approval Workflow

**Zero Trust for External Actions:**

```
Agent Creates Draft          Human Reviews              Agent Executes
       │                          │                          │
       ▼                          ▼                          ▼
┌──────────────┐          ┌──────────────┐          ┌──────────────┐
│ /Pending_    │  ──────▶ │  Move to     │  ──────▶ │ Detect &     │
│  Approval/   │          │  /Approved/  │          │ Execute      │
└──────────────┘          └──────────────┘          └──────────────┘
```

- All social media posts require approval
- All external API calls are logged
- Full content preview before execution
- Immutable audit trail

### 4. Universal Audit Logging System

**Multi-Format, Multi-Destination Logging:**

```python
audit_logger = get_logger(ServiceSource.ODOO_SERVER)

audit_logger.success(
    "Invoice created",
    action=ActionType.DATA_WRITE,
    details={"invoice_id": 12345, "amount": 5000.00}
)
```

**Output Destinations:**
- `Logs/master_audit.md` - Human-readable Markdown
- `Logs/audit.json` - Machine-queryable JSON
- `Logs/errors.md` - Dedicated error log
- Console - Color-coded real-time output

### 5. Modular MCP Server Architecture

**Model Context Protocol (MCP) Servers:**

Each integration domain is isolated in its own FastAPI server:

| Server | Port | Responsibility |
|--------|------|----------------|
| `mcp_odoo_server.py` | 8001 | ERP operations (invoices, expenses) |
| `mcp_social_media_server.py` | 8002 | Facebook/Instagram publishing |
| `mcp_x_publisher.py` | 8003 | X (Twitter) posting & analytics |

**Benefits:**
- Independent scaling
- Isolated failure domains
- Easy to add new integrations
- Consistent API patterns

### 6. Type-Safe Data Models

**Pydantic Models for Runtime Validation:**

```python
class CreateInvoiceRequest(BaseModel):
    partner_id: int = Field(..., description="Customer/Vendor ID")
    invoice_type: str = Field(default="out_invoice")
    lines: list[InvoiceLineItem] = Field(..., min_length=1)

    # Automatic validation, serialization, documentation
```

### 7. Async-First Design

**Full Async/Await Pattern:**

```python
# Concurrent data collection
financial, marketing, operations = await asyncio.gather(
    self.collect_financial_data(),
    self.collect_marketing_data(),
    self.collect_operational_data()
)
```

---

## Project Architecture

```
Gold Tier/
│
├── core/                          # Core automation engine
│   ├── ralph_loop.py              # Autonomous loop controller
│   ├── logger.py                  # Universal audit system
│   └── skills/                    # Agent capabilities
│       └── weekly_ceo_briefing.py # Executive report skill
│
├── mcp_servers/                   # FastAPI microservices
│   ├── mcp_odoo_server.py         # Odoo ERP integration
│   ├── mcp_social_media_server.py # Meta platforms
│   ├── mcp_x_publisher.py         # X/Twitter
│   └── error_handler.py           # Shared error utilities
│
├── Needs_Action/                  # Task input queue
├── Pending_Approval/              # Human review queue
├── Approved/                      # Execution queue
├── Rejected/                      # Rejection archive
├── Reports/                       # Generated outputs
├── Logs/                          # Audit trail
│
├── .env                           # Secrets (git-ignored)
├── Company_Handbook.md            # Business context
├── ARCHITECTURE.md                # Technical documentation
└── README.md                      # This file
```

**Why This Structure?**

| Principle | Implementation |
|-----------|----------------|
| **Separation of Concerns** | Each MCP server handles one domain |
| **Scalability** | Add new skills/servers without touching core |
| **Auditability** | File-based workflow creates paper trail |
| **Simplicity** | No database required; files are the database |
| **Transparency** | Markdown logs readable by humans |

---

## Core Functionalities

### 1. Autonomous Task Processing
- Scans `/Needs_Action/` for task files
- Parses Markdown to extract task type and dependencies
- Routes to appropriate MCP server
- Handles failures with automatic retry

### 2. Financial Operations (Odoo)
- Create customer/vendor invoices
- Log expense records
- Generate weekly financial summaries
- Full audit trail for compliance

### 3. Social Media Management
- Draft posts for Facebook/Instagram
- Generate AI-powered tweet content
- Publish only after human approval
- Track engagement analytics

### 4. Executive Reporting
- Aggregate data from all sources
- Generate CEO Weekly Briefing
- Identify operational risks
- Provide strategic recommendations

### 5. Error Recovery
- 3-retry with exponential backoff
- Auto-save failed tasks for retry
- Categorize errors by severity
- Alert on critical failures

---

## How to Run (Step-by-Step)

### Prerequisites

- Python 3.11+
- pip (package manager)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/gold-tier-autonomous-employee.git
cd gold-tier-autonomous-employee
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install fastapi uvicorn httpx python-dotenv pydantic tweepy
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Odoo Configuration
ODOO_URL=https://your-odoo-instance.com
ODOO_DB=your_database
ODOO_USERNAME=admin
ODOO_PASSWORD=your_password

# Facebook/Instagram
FB_ACCESS_TOKEN=your_access_token
FB_PAGE_ID=your_page_id
IG_BUSINESS_ID=your_instagram_business_id

# X (Twitter)
X_API_KEY=your_api_key
X_API_SECRET=your_api_secret
X_ACCESS_TOKEN=your_access_token
X_ACCESS_TOKEN_SECRET=your_access_token_secret
X_BEARER_TOKEN=your_bearer_token

# Company
COMPANY_NAME=Your Company Name
```

### 5. Start MCP Servers

Open 3 terminal windows:

**Terminal 1 - Odoo Server:**
```bash
cd mcp_servers
python mcp_odoo_server.py
# Running on http://localhost:8001
```

**Terminal 2 - Social Media Server:**
```bash
cd mcp_servers
python mcp_social_media_server.py
# Running on http://localhost:8002
```

**Terminal 3 - X Publisher Server:**
```bash
cd mcp_servers
python mcp_x_publisher.py
# Running on http://localhost:8003
```

### 6. Start RALPH Loop

**Terminal 4 - Core Agent:**
```bash
cd core
python ralph_loop.py
```

### 7. Verify Health

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

### 8. Generate CEO Briefing (Optional)

```bash
cd core/skills
python weekly_ceo_briefing.py
# Output: Reports/CEO_Weekly_Briefing.md
```

---

## API Documentation

Once servers are running, access interactive API docs:

| Server | Swagger UI | ReDoc |
|--------|------------|-------|
| Odoo | http://localhost:8001/docs | http://localhost:8001/redoc |
| Social | http://localhost:8002/docs | http://localhost:8002/redoc |
| X Publisher | http://localhost:8003/docs | http://localhost:8003/redoc |

---

## Technology Stack

| Category | Technology |
|----------|------------|
| **Language** | Python 3.11+ |
| **Framework** | FastAPI |
| **HTTP Client** | httpx (async) |
| **Validation** | Pydantic v2 |
| **Twitter API** | Tweepy |
| **Task Format** | Markdown |
| **Logging** | Custom multi-format logger |
| **Architecture** | MCP (Model Context Protocol) |

---

## Security Considerations

- All credentials stored in `.env` (git-ignored)
- Human approval required for all external actions
- Full audit trail for compliance
- Input validation via Pydantic
- No hardcoded secrets in codebase

---

## Future Roadmap

- [ ] Web dashboard for approvals
- [ ] PostgreSQL for task storage
- [ ] Email MCP server
- [ ] Slack integration
- [ ] Docker containerization
- [ ] Kubernetes deployment
- [ ] Unit test suite

---

## Author

Built for **Hackathon 0 - Gold Tier Challenge**

---

## License

MIT License - See [LICENSE](LICENSE) for details.

---

*"The Gold Standard in Autonomous Business Automation"*
