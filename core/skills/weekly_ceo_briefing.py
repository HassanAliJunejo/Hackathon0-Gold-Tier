"""
Agent Skill: weekly_ceo_briefing

Gathers enterprise data and generates a professional CEO weekly briefing report.

Data Sources:
- Odoo ERP: Financial summary (revenue, expenses, cash flow)
- Social Media: Marketing analytics
- Email Activity: Communication metrics
- RALPH Loop: Completed tasks and operations

Output: /Reports/CEO_Weekly_Briefing.md
Return: CEO_BRIEFING_READY
"""

import os
import json
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

BASE_DIR = Path(__file__).parent.parent.parent
REPORTS_DIR = BASE_DIR / "Reports"
LOGS_DIR = BASE_DIR / "Logs"

MCP_SERVERS = {
    "odoo": os.getenv("MCP_ODOO_URL", "http://localhost:8001"),
    "social": os.getenv("MCP_SOCIAL_URL", "http://localhost:8002"),
}

# Report configuration
REPORT_FILE = REPORTS_DIR / "CEO_Weekly_Briefing.md"
COMPANY_NAME = os.getenv("COMPANY_NAME", "Organization")


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class FinancialData:
    total_revenue: float = 0.0
    total_expenses: float = 0.0
    net_income: float = 0.0
    cash_flow: float = 0.0
    invoices_created: int = 0
    invoices_paid: int = 0
    collection_rate: float = 0.0
    top_customers: List[Dict] = field(default_factory=list)
    top_expense_categories: List[Dict] = field(default_factory=list)
    period_start: str = ""
    period_end: str = ""


@dataclass
class MarketingData:
    total_posts: int = 0
    facebook_posts: int = 0
    instagram_posts: int = 0
    pending_approvals: int = 0
    engagement_summary: str = ""


@dataclass
class OperationalData:
    tasks_completed: int = 0
    tasks_failed: int = 0
    active_approvals: int = 0
    automation_uptime: str = "Operational"
    recent_actions: List[str] = field(default_factory=list)


@dataclass
class EmailData:
    emails_sent: int = 0
    emails_received: int = 0
    response_rate: float = 0.0
    avg_response_time: str = "N/A"


@dataclass
class CEOBriefingData:
    financial: FinancialData = field(default_factory=FinancialData)
    marketing: MarketingData = field(default_factory=MarketingData)
    operations: OperationalData = field(default_factory=OperationalData)
    email: EmailData = field(default_factory=EmailData)
    generated_at: str = ""
    period: str = ""


# =============================================================================
# Data Collectors
# =============================================================================

class DataCollector:
    """Collects data from all enterprise sources."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def collect_financial_data(self) -> FinancialData:
        """Fetch financial summary from Odoo MCP server."""
        try:
            response = await self.client.get(
                f"{MCP_SERVERS['odoo']}/weekly-financial-summary"
            )

            if response.status_code == 200:
                data = response.json()

                # Calculate collection rate
                collection_rate = 0.0
                if data.get("invoices_created", 0) > 0:
                    collection_rate = (data.get("invoices_paid", 0) / data["invoices_created"]) * 100

                # Estimate cash flow (revenue collected - expenses paid)
                cash_flow = (data.get("total_revenue", 0) * (collection_rate / 100)) - data.get("total_expenses", 0)

                return FinancialData(
                    total_revenue=data.get("total_revenue", 0),
                    total_expenses=data.get("total_expenses", 0),
                    net_income=data.get("net_income", 0),
                    cash_flow=cash_flow,
                    invoices_created=data.get("invoices_created", 0),
                    invoices_paid=data.get("invoices_paid", 0),
                    collection_rate=collection_rate,
                    top_customers=data.get("top_customers", []),
                    top_expense_categories=data.get("top_expense_categories", []),
                    period_start=data.get("period_start", ""),
                    period_end=data.get("period_end", "")
                )

        except Exception as e:
            print(f"[WARNING] Failed to fetch financial data: {e}")

        # Return empty data with current period
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        return FinancialData(
            period_start=start_date.strftime("%Y-%m-%d"),
            period_end=end_date.strftime("%Y-%m-%d")
        )

    async def collect_marketing_data(self) -> MarketingData:
        """Fetch social media analytics from Social MCP server."""
        try:
            response = await self.client.get(
                f"{MCP_SERVERS['social']}/post-summary"
            )

            if response.status_code == 200:
                data = response.json()
                return MarketingData(
                    total_posts=data.get("total_posts", 0),
                    facebook_posts=data.get("facebook_posts", 0),
                    instagram_posts=data.get("instagram_posts", 0),
                    pending_approvals=data.get("pending_approvals", 0),
                    engagement_summary=self._generate_engagement_summary(data)
                )

        except Exception as e:
            print(f"[WARNING] Failed to fetch marketing data: {e}")

        return MarketingData()

    def _generate_engagement_summary(self, data: Dict) -> str:
        """Generate human-readable engagement summary."""
        total = data.get("total_posts", 0)
        if total == 0:
            return "No social media activity this period."

        fb = data.get("facebook_posts", 0)
        ig = data.get("instagram_posts", 0)

        parts = []
        if fb > 0:
            parts.append(f"{fb} Facebook post{'s' if fb != 1 else ''}")
        if ig > 0:
            parts.append(f"{ig} Instagram post{'s' if ig != 1 else ''}")

        return f"Published {' and '.join(parts)} this week."

    async def collect_operational_data(self) -> OperationalData:
        """Collect operational data from RALPH loop logs."""
        operations = OperationalData()

        # Parse RALPH loop log
        ralph_log = LOGS_DIR / "ralph_loop.md"
        if ralph_log.exists():
            try:
                content = ralph_log.read_text(encoding="utf-8")
                operations.tasks_completed = content.count("[SUCCESS]")
                operations.tasks_failed = content.count("[ERROR]")

                # Extract recent actions (last 5)
                lines = content.split("\n")
                actions = [l for l in lines if l.startswith("## [")]
                operations.recent_actions = actions[-5:] if actions else []

            except Exception as e:
                print(f"[WARNING] Failed to parse RALPH log: {e}")

        # Check pending approvals
        pending_dir = BASE_DIR / "Pending_Approval"
        if pending_dir.exists():
            operations.active_approvals = len(list(pending_dir.glob("APPROVAL-*.md")))

        return operations

    async def collect_email_data(self) -> EmailData:
        """Collect email activity metrics."""
        # Placeholder - integrate with email MCP server when available
        return EmailData(
            emails_sent=0,
            emails_received=0,
            response_rate=0.0,
            avg_response_time="N/A"
        )

    async def collect_all(self) -> CEOBriefingData:
        """Collect data from all sources concurrently."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        period = f"{start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}"

        # Collect all data in parallel
        financial, marketing, operations, email = await asyncio.gather(
            self.collect_financial_data(),
            self.collect_marketing_data(),
            self.collect_operational_data(),
            self.collect_email_data()
        )

        return CEOBriefingData(
            financial=financial,
            marketing=marketing,
            operations=operations,
            email=email,
            generated_at=datetime.now().isoformat(),
            period=period
        )


# =============================================================================
# Risk Analyzer
# =============================================================================

class RiskAnalyzer:
    """Analyzes data to identify operational risks."""

    def analyze(self, data: CEOBriefingData) -> List[Dict[str, str]]:
        """Identify and categorize operational risks."""
        risks = []

        # Financial risks
        if data.financial.collection_rate < 70:
            risks.append({
                "category": "Financial",
                "severity": "HIGH",
                "description": f"Invoice collection rate at {data.financial.collection_rate:.1f}% - below 70% threshold",
                "recommendation": "Review accounts receivable aging and implement collection follow-ups"
            })

        if data.financial.net_income < 0:
            risks.append({
                "category": "Financial",
                "severity": "HIGH",
                "description": f"Negative net income: ${data.financial.net_income:,.2f}",
                "recommendation": "Review expense categories and identify cost reduction opportunities"
            })

        if data.financial.cash_flow < 0:
            risks.append({
                "category": "Financial",
                "severity": "MEDIUM",
                "description": "Negative cash flow position",
                "recommendation": "Accelerate collections and review payment terms with vendors"
            })

        # Operational risks
        if data.operations.tasks_failed > 3:
            risks.append({
                "category": "Operations",
                "severity": "MEDIUM",
                "description": f"{data.operations.tasks_failed} task failures this period",
                "recommendation": "Review error logs and address recurring issues"
            })

        if data.operations.active_approvals > 10:
            risks.append({
                "category": "Operations",
                "severity": "LOW",
                "description": f"{data.operations.active_approvals} items pending approval",
                "recommendation": "Clear approval backlog to maintain operational velocity"
            })

        # Marketing risks
        if data.marketing.total_posts == 0:
            risks.append({
                "category": "Marketing",
                "severity": "LOW",
                "description": "No social media activity this period",
                "recommendation": "Review content calendar and publishing schedule"
            })

        return risks


# =============================================================================
# Recommendation Engine
# =============================================================================

class RecommendationEngine:
    """Generates strategic recommendations based on data analysis."""

    def generate(self, data: CEOBriefingData, risks: List[Dict]) -> List[str]:
        """Generate executive recommendations."""
        recommendations = []

        # Revenue recommendations
        if data.financial.total_revenue > 0:
            if data.financial.top_customers:
                top_customer = data.financial.top_customers[0].get("name", "Unknown")
                recommendations.append(
                    f"**Customer Concentration**: Top customer ({top_customer}) represents significant revenue. "
                    f"Consider diversification strategies to reduce dependency."
                )

        # Expense recommendations
        if data.financial.top_expense_categories:
            top_expense = data.financial.top_expense_categories[0]
            recommendations.append(
                f"**Cost Management**: Largest expense category is '{top_expense.get('category', 'Unknown')}' "
                f"at ${top_expense.get('total', 0):,.2f}. Review for optimization opportunities."
            )

        # Marketing recommendations
        if data.marketing.total_posts < 3:
            recommendations.append(
                "**Digital Presence**: Social media activity is below target. "
                "Increase posting frequency to maintain audience engagement."
            )

        # Operational recommendations
        if data.operations.tasks_completed > 0:
            success_rate = (data.operations.tasks_completed /
                          (data.operations.tasks_completed + data.operations.tasks_failed)) * 100
            if success_rate > 90:
                recommendations.append(
                    f"**Automation Performance**: {success_rate:.0f}% task success rate demonstrates "
                    f"strong operational efficiency. Consider expanding automation scope."
                )

        # Risk-based recommendations
        high_risks = [r for r in risks if r["severity"] == "HIGH"]
        if high_risks:
            recommendations.append(
                f"**Priority Action Required**: {len(high_risks)} high-severity risk(s) identified. "
                f"Immediate attention recommended."
            )

        # Default recommendation
        if not recommendations:
            recommendations.append(
                "**Steady State**: Operations are running within normal parameters. "
                "Continue monitoring key metrics for emerging trends."
            )

        return recommendations


# =============================================================================
# Report Generator
# =============================================================================

class ReportGenerator:
    """Generates the CEO Weekly Briefing report."""

    def __init__(self):
        self.risk_analyzer = RiskAnalyzer()
        self.recommendation_engine = RecommendationEngine()

    def generate(self, data: CEOBriefingData) -> str:
        """Generate the complete CEO briefing report."""
        risks = self.risk_analyzer.analyze(data)
        recommendations = self.recommendation_engine.generate(data, risks)

        report = f"""# CEO Weekly Briefing

**{COMPANY_NAME}**
**Period:** {data.period}
**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

---

## Executive Summary

This briefing provides a comprehensive overview of {COMPANY_NAME}'s performance for the reporting period, including financial metrics, marketing activities, and operational status.

---

## 1. Revenue

| Metric | Value |
|--------|-------|
| **Total Revenue** | ${data.financial.total_revenue:,.2f} |
| **Invoices Created** | {data.financial.invoices_created} |
| **Invoices Paid** | {data.financial.invoices_paid} |
| **Collection Rate** | {data.financial.collection_rate:.1f}% |

### Top Customers by Revenue

{self._format_top_customers(data.financial.top_customers)}

---

## 2. Expenses

| Metric | Value |
|--------|-------|
| **Total Expenses** | ${data.financial.total_expenses:,.2f} |
| **Net Income** | ${data.financial.net_income:,.2f} |
| **Profit Margin** | {self._calculate_margin(data.financial):.1f}% |

### Top Expense Categories

{self._format_expense_categories(data.financial.top_expense_categories)}

---

## 3. Cash Flow

| Metric | Value |
|--------|-------|
| **Cash Flow Position** | ${data.financial.cash_flow:,.2f} |
| **Status** | {self._cash_flow_status(data.financial.cash_flow)} |

**Analysis:** {self._cash_flow_analysis(data.financial)}

---

## 4. Marketing Performance

| Platform | Posts | Status |
|----------|-------|--------|
| **Facebook** | {data.marketing.facebook_posts} | Active |
| **Instagram** | {data.marketing.instagram_posts} | Active |
| **Total** | {data.marketing.total_posts} | - |
| **Pending Approvals** | {data.marketing.pending_approvals} | - |

**Summary:** {data.marketing.engagement_summary if data.marketing.engagement_summary else 'No activity recorded.'}

---

## 5. Operational Risks

{self._format_risks(risks)}

---

## 6. Recommendations

{self._format_recommendations(recommendations)}

---

## Appendix: Operational Metrics

| Metric | Value |
|--------|-------|
| **Tasks Completed** | {data.operations.tasks_completed} |
| **Tasks Failed** | {data.operations.tasks_failed} |
| **Automation Status** | {data.operations.automation_uptime} |
| **Pending Approvals** | {data.operations.active_approvals} |

---

*This report was automatically generated by the RALPH Autonomous Agent System.*
*For questions or clarifications, contact your system administrator.*

"""
        return report

    def _format_top_customers(self, customers: List[Dict]) -> str:
        if not customers:
            return "*No customer data available for this period.*"

        rows = ["| Rank | Customer | Revenue |", "|------|----------|---------|"]
        for i, c in enumerate(customers[:5], 1):
            rows.append(f"| {i} | {c.get('name', 'Unknown')} | ${c.get('total', 0):,.2f} |")
        return "\n".join(rows)

    def _format_expense_categories(self, categories: List[Dict]) -> str:
        if not categories:
            return "*No expense data available for this period.*"

        rows = ["| Category | Amount |", "|----------|--------|"]
        for c in categories[:5]:
            rows.append(f"| {c.get('category', 'Unknown')} | ${c.get('total', 0):,.2f} |")
        return "\n".join(rows)

    def _calculate_margin(self, financial: FinancialData) -> float:
        if financial.total_revenue == 0:
            return 0.0
        return (financial.net_income / financial.total_revenue) * 100

    def _cash_flow_status(self, cash_flow: float) -> str:
        if cash_flow > 0:
            return "✅ Positive"
        elif cash_flow < 0:
            return "⚠️ Negative"
        return "➖ Neutral"

    def _cash_flow_analysis(self, financial: FinancialData) -> str:
        if financial.cash_flow > 0:
            return (
                f"Cash flow is positive at ${financial.cash_flow:,.2f}. "
                f"The organization is generating sufficient cash to cover operations."
            )
        elif financial.cash_flow < 0:
            return (
                f"Cash flow is negative at ${financial.cash_flow:,.2f}. "
                f"Review collection efforts and expense timing to improve position."
            )
        return "Cash flow is neutral. Monitor closely for changes."

    def _format_risks(self, risks: List[Dict]) -> str:
        if not risks:
            return "✅ **No significant risks identified this period.**\n\nOperations are running within normal parameters."

        sections = []
        for risk in risks:
            severity_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(risk["severity"], "⚪")
            sections.append(
                f"### {severity_icon} {risk['category']} Risk ({risk['severity']})\n\n"
                f"**Issue:** {risk['description']}\n\n"
                f"**Recommendation:** {risk['recommendation']}\n"
            )

        return "\n".join(sections)

    def _format_recommendations(self, recommendations: List[str]) -> str:
        if not recommendations:
            return "*No specific recommendations at this time.*"

        items = [f"{i}. {rec}" for i, rec in enumerate(recommendations, 1)]
        return "\n\n".join(items)


# =============================================================================
# Main Skill Execution
# =============================================================================

async def execute() -> str:
    """
    Execute the weekly CEO briefing skill.

    Returns: CEO_BRIEFING_READY
    """
    print("\n" + "=" * 60)
    print("  WEEKLY CEO BRIEFING - Data Collection & Report Generation")
    print("=" * 60 + "\n")

    # Ensure reports directory exists
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize collectors
    collector = DataCollector()
    generator = ReportGenerator()

    try:
        # Step 1: Collect all data
        print("[1/4] Collecting financial data from Odoo...")
        print("[2/4] Collecting marketing data from Social Media...")
        print("[3/4] Collecting operational data from RALPH logs...")
        print("[4/4] Collecting email activity metrics...")

        data = await collector.collect_all()
        print("\n✓ Data collection complete\n")

        # Step 2: Generate report
        print("Generating CEO Weekly Briefing...")
        report = generator.generate(data)

        # Step 3: Save report
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"✓ Report saved to: {REPORT_FILE}\n")

        # Step 4: Summary
        print("=" * 60)
        print("  BRIEFING SUMMARY")
        print("=" * 60)
        print(f"  Period: {data.period}")
        print(f"  Revenue: ${data.financial.total_revenue:,.2f}")
        print(f"  Expenses: ${data.financial.total_expenses:,.2f}")
        print(f"  Net Income: ${data.financial.net_income:,.2f}")
        print(f"  Marketing Posts: {data.marketing.total_posts}")
        print(f"  Tasks Completed: {data.operations.tasks_completed}")
        print("=" * 60 + "\n")

        return "CEO_BRIEFING_READY"

    except Exception as e:
        print(f"\n[ERROR] Failed to generate briefing: {e}")
        raise

    finally:
        await collector.close()


# =============================================================================
# Entry Point
# =============================================================================

def run() -> str:
    """Synchronous entry point for the skill."""
    return asyncio.run(execute())


if __name__ == "__main__":
    result = run()
    print(f"\nResult: {result}")
