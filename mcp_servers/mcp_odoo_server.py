"""
MCP Odoo Server - Gold Tier Autonomous Employee
FastAPI server for Odoo ERP integration via JSON-RPC API
"""

import os
import json
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Any
from pathlib import Path
from functools import wraps

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
audit_logger = get_logger(ServiceSource.ODOO_SERVER)

# =============================================================================
# Configuration
# =============================================================================

ODOO_URL = os.getenv("ODOO_URL", "https://your-odoo-instance.com")
ODOO_DB = os.getenv("ODOO_DB", "your_database")
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin_password")

MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

LOG_DIR = Path(__file__).parent.parent / "Logs"
LOG_FILE = LOG_DIR / "odoo_log.md"

# Initialize error handler
error_handler = MCPErrorHandler("odoo")

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
    title="MCP Odoo Server",
    description="Gold Tier Autonomous Employee - Odoo ERP Integration",
    version="1.0.0"
)

# =============================================================================
# Pydantic Models
# =============================================================================

class InvoiceLineItem(BaseModel):
    product_id: int = Field(..., description="Odoo product ID")
    quantity: float = Field(default=1.0, ge=0)
    price_unit: float = Field(..., ge=0)
    name: Optional[str] = Field(default=None, description="Line description")


class CreateInvoiceRequest(BaseModel):
    partner_id: int = Field(..., description="Customer/Vendor ID in Odoo")
    invoice_type: str = Field(default="out_invoice", description="out_invoice (customer) or in_invoice (vendor)")
    invoice_date: Optional[str] = Field(default=None, description="Invoice date (YYYY-MM-DD)")
    due_date: Optional[str] = Field(default=None, description="Due date (YYYY-MM-DD)")
    lines: list[InvoiceLineItem] = Field(..., min_length=1)
    reference: Optional[str] = Field(default=None, description="External reference")


class CreateExpenseRequest(BaseModel):
    employee_id: int = Field(..., description="Employee ID in Odoo")
    product_id: int = Field(..., description="Expense product/category ID")
    name: str = Field(..., description="Expense description")
    unit_amount: float = Field(..., ge=0, description="Expense amount")
    quantity: float = Field(default=1.0, ge=0)
    date: Optional[str] = Field(default=None, description="Expense date (YYYY-MM-DD)")
    reference: Optional[str] = Field(default=None, description="Receipt reference")
    payment_mode: str = Field(default="own_account", description="own_account or company_account")


class OdooResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None
    odoo_id: Optional[int] = None


class FinancialSummary(BaseModel):
    success: bool
    message: str
    period_start: str
    period_end: str
    total_revenue: float
    total_expenses: float
    net_income: float
    invoices_created: int
    invoices_paid: int
    expenses_count: int
    top_customers: list[dict]
    top_expense_categories: list[dict]


# =============================================================================
# Logging Utility
# =============================================================================

async def log_transaction(
    action: str,
    status: str,
    details: dict,
    error: Optional[str] = None
) -> None:
    """Log transaction to odoo_log.md with audit trail."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

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

    # Append to log file
    mode = "a" if LOG_FILE.exists() else "w"
    if mode == "w":
        header = "# Odoo Transaction Log\n\nAll external actions are logged for audit compliance.\n\n"
        log_entry = header + log_entry

    with open(LOG_FILE, mode, encoding="utf-8") as f:
        f.write(log_entry)


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
                        wait_time = delay * (2 ** (attempt - 1))  # Exponential backoff
                        await asyncio.sleep(wait_time)
                    continue

            # All retries exhausted
            raise last_exception
        return wrapper
    return decorator


# =============================================================================
# Odoo JSON-RPC Client
# =============================================================================

class OdooClient:
    """Async Odoo JSON-RPC client with retry logic."""

    def __init__(self):
        self.url = ODOO_URL
        self.db = ODOO_DB
        self.username = ODOO_USERNAME
        self.password = ODOO_PASSWORD
        self.uid: Optional[int] = None

    async def _jsonrpc_call(
        self,
        endpoint: str,
        service: str,
        method: str,
        args: list
    ) -> Any:
        """Make JSON-RPC call to Odoo."""
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": service,
                "method": method,
                "args": args
            },
            "id": int(datetime.now().timestamp() * 1000)
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.url}{endpoint}",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                error_msg = result["error"].get("data", {}).get("message", str(result["error"]))
                raise Exception(f"Odoo Error: {error_msg}")

            return result.get("result")

    @with_enhanced_retry(
        service="odoo",
        action="authenticate",
        config=RetryConfig(max_retries=MAX_RETRIES),
        timeout_config=TIMEOUT_CONFIG
    )
    async def authenticate(self) -> int:
        """Authenticate with Odoo and get user ID."""
        self.uid = await self._jsonrpc_call(
            "/jsonrpc",
            "common",
            "authenticate",
            [self.db, self.username, self.password, {}]
        )

        if not self.uid:
            raise Exception("Authentication failed: Invalid credentials")

        return self.uid

    @with_enhanced_retry(
        service="odoo",
        action="execute_kw",
        config=RetryConfig(max_retries=MAX_RETRIES),
        timeout_config=TIMEOUT_CONFIG
    )
    async def execute_kw(
        self,
        model: str,
        method: str,
        args: list,
        kwargs: Optional[dict] = None
    ) -> Any:
        """Execute Odoo model method."""
        if not self.uid:
            await self.authenticate()

        return await self._jsonrpc_call(
            "/jsonrpc",
            "object",
            "execute_kw",
            [
                self.db,
                self.uid,
                self.password,
                model,
                method,
                args,
                kwargs or {}
            ]
        )

    async def create_record(self, model: str, values: dict) -> int:
        """Create a new record in Odoo."""
        return await self.execute_kw(model, "create", [values])

    async def search_read(
        self,
        model: str,
        domain: list,
        fields: list,
        limit: Optional[int] = None,
        order: Optional[str] = None
    ) -> list:
        """Search and read records from Odoo."""
        kwargs = {"fields": fields}
        if limit:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order

        return await self.execute_kw(model, "search_read", [domain], kwargs)


# Global client instance
odoo_client = OdooClient()


# =============================================================================
# API Endpoints
# =============================================================================

@app.post("/create-invoice", response_model=OdooResponse)
async def create_invoice(request: CreateInvoiceRequest):
    """
    Create a new invoice in Odoo.

    Supports both customer invoices (out_invoice) and vendor bills (in_invoice).
    All transactions are logged for audit compliance.
    Implements 3-retry policy before failure.
    """
    action = "Create Invoice"
    details = request.model_dump()

    # Log to universal audit logger
    audit_logger.info(
        f"Creating invoice for partner {request.partner_id}",
        action=ActionType.DATA_WRITE,
        details=details
    )

    try:
        # Prepare invoice lines
        invoice_lines = []
        for line in request.lines:
            line_vals = {
                "product_id": line.product_id,
                "quantity": line.quantity,
                "price_unit": line.price_unit,
            }
            if line.name:
                line_vals["name"] = line.name
            invoice_lines.append((0, 0, line_vals))

        # Prepare invoice values
        invoice_vals = {
            "partner_id": request.partner_id,
            "move_type": request.invoice_type,
            "invoice_line_ids": invoice_lines,
        }

        if request.invoice_date:
            invoice_vals["invoice_date"] = request.invoice_date
        if request.due_date:
            invoice_vals["invoice_date_due"] = request.due_date
        if request.reference:
            invoice_vals["ref"] = request.reference

        # Create invoice in Odoo
        invoice_id = await odoo_client.create_record("account.move", invoice_vals)

        # Log success
        await log_transaction(
            action=action,
            status="SUCCESS",
            details={**details, "odoo_invoice_id": invoice_id}
        )

        # Log to universal audit logger
        audit_logger.success(
            f"Invoice created: {invoice_id}",
            action=ActionType.DATA_WRITE,
            details={"invoice_id": invoice_id, "partner_id": request.partner_id}
        )

        return OdooResponse(
            success=True,
            message=f"Invoice created successfully",
            data={"invoice_type": request.invoice_type},
            odoo_id=invoice_id
        )

    except Exception as e:
        error_msg = str(e)

        # Log failure
        await log_transaction(
            action=action,
            status="FAILED",
            details=details,
            error=error_msg
        )

        # Use enhanced error handler - save to Needs_Action for retry
        error_result = error_handler.handle(
            error=e,
            action=action,
            request_data=details,
            save_for_retry=True
        )

        return OdooResponse(
            success=False,
            message=f"Failed to create invoice after {MAX_RETRIES} attempts. Task saved for retry: {error_result.needs_action_file}",
            data={"error_details": error_msg, "retry_file": error_result.needs_action_file}
        )


@app.post("/create-expense", response_model=OdooResponse)
async def create_expense(request: CreateExpenseRequest):
    """
    Create a new expense record in Odoo.

    Creates expense entries for employee reimbursement or company expenses.
    All transactions are logged for audit compliance.
    Implements 3-retry policy before failure.
    """
    action = "Create Expense"
    details = request.model_dump()

    try:
        # Prepare expense values
        expense_vals = {
            "employee_id": request.employee_id,
            "product_id": request.product_id,
            "name": request.name,
            "unit_amount": request.unit_amount,
            "quantity": request.quantity,
            "payment_mode": request.payment_mode,
        }

        if request.date:
            expense_vals["date"] = request.date
        else:
            expense_vals["date"] = datetime.now().strftime("%Y-%m-%d")

        if request.reference:
            expense_vals["reference"] = request.reference

        # Create expense in Odoo
        expense_id = await odoo_client.create_record("hr.expense", expense_vals)

        # Log success
        await log_transaction(
            action=action,
            status="SUCCESS",
            details={**details, "odoo_expense_id": expense_id}
        )

        return OdooResponse(
            success=True,
            message=f"Expense created successfully",
            data={"total_amount": request.unit_amount * request.quantity},
            odoo_id=expense_id
        )

    except Exception as e:
        error_msg = str(e)

        # Log failure
        await log_transaction(
            action=action,
            status="FAILED",
            details=details,
            error=error_msg
        )

        # Use enhanced error handler - save to Needs_Action for retry
        error_result = error_handler.handle(
            error=e,
            action=action,
            request_data=details,
            save_for_retry=True
        )

        return OdooResponse(
            success=False,
            message=f"Failed to create expense after {MAX_RETRIES} attempts. Task saved for retry: {error_result.needs_action_file}",
            data={"error_details": error_msg, "retry_file": error_result.needs_action_file}
        )


@app.get("/weekly-financial-summary", response_model=FinancialSummary)
async def get_weekly_financial_summary():
    """
    Get weekly financial summary from Odoo.

    Retrieves:
    - Total revenue and expenses
    - Invoice statistics
    - Top customers and expense categories

    All queries are logged for audit compliance.
    Implements 3-retry policy before failure.
    """
    action = "Weekly Financial Summary"

    # Calculate date range (last 7 days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    period_start = start_date.strftime("%Y-%m-%d")
    period_end = end_date.strftime("%Y-%m-%d")

    details = {"period_start": period_start, "period_end": period_end}

    try:
        # Fetch customer invoices (revenue)
        invoices = await odoo_client.search_read(
            model="account.move",
            domain=[
                ("move_type", "=", "out_invoice"),
                ("invoice_date", ">=", period_start),
                ("invoice_date", "<=", period_end),
            ],
            fields=["id", "partner_id", "amount_total", "state", "payment_state"]
        )

        total_revenue = sum(inv["amount_total"] for inv in invoices)
        invoices_created = len(invoices)
        invoices_paid = sum(1 for inv in invoices if inv.get("payment_state") == "paid")

        # Calculate top customers
        customer_totals: dict[str, float] = {}
        for inv in invoices:
            partner_name = inv["partner_id"][1] if inv.get("partner_id") else "Unknown"
            customer_totals[partner_name] = customer_totals.get(partner_name, 0) + inv["amount_total"]

        top_customers = [
            {"name": name, "total": total}
            for name, total in sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        # Fetch expenses
        expenses = await odoo_client.search_read(
            model="hr.expense",
            domain=[
                ("date", ">=", period_start),
                ("date", "<=", period_end),
            ],
            fields=["id", "product_id", "total_amount", "name"]
        )

        total_expenses = sum(exp["total_amount"] for exp in expenses)
        expenses_count = len(expenses)

        # Calculate top expense categories
        category_totals: dict[str, float] = {}
        for exp in expenses:
            category = exp["product_id"][1] if exp.get("product_id") else "Uncategorized"
            category_totals[category] = category_totals.get(category, 0) + exp["total_amount"]

        top_expense_categories = [
            {"category": cat, "total": total}
            for cat, total in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        # Calculate net income
        net_income = total_revenue - total_expenses

        # Log success
        await log_transaction(
            action=action,
            status="SUCCESS",
            details={
                **details,
                "total_revenue": total_revenue,
                "total_expenses": total_expenses,
                "net_income": net_income
            }
        )

        return FinancialSummary(
            success=True,
            message="Weekly financial summary retrieved successfully",
            period_start=period_start,
            period_end=period_end,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            net_income=net_income,
            invoices_created=invoices_created,
            invoices_paid=invoices_paid,
            expenses_count=expenses_count,
            top_customers=top_customers,
            top_expense_categories=top_expense_categories
        )

    except Exception as e:
        error_msg = str(e)

        # Log failure
        await log_transaction(
            action=action,
            status="FAILED",
            details=details,
            error=error_msg
        )

        return FinancialSummary(
            success=False,
            message=f"Failed to retrieve summary after {MAX_RETRIES} attempts. Please try again later.",
            period_start=period_start,
            period_end=period_end,
            total_revenue=0,
            total_expenses=0,
            net_income=0,
            invoices_created=0,
            invoices_paid=0,
            expenses_count=0,
            top_customers=[],
            top_expense_categories=[]
        )


# =============================================================================
# Health Check
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "MCP Odoo Server",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "MCP Odoo Server",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }


# =============================================================================
# Startup Event
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    await log_transaction(
        action="Server Startup",
        status="INFO",
        details={"message": "MCP Odoo Server started", "odoo_url": ODOO_URL}
    )


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
