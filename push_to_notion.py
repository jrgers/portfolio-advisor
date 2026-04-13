"""
Push the weekly portfolio report to Notion.

Reads weekly_report.json from the current directory and creates a new
page in the Weekly Reports Notion database.

Environment variables required:
    NOTION_TOKEN         — Notion integration token (secret)
    NOTION_DATABASE_ID   — ID of the Weekly Reports database
"""

import json
import os
import sys
import urllib.request
import urllib.error

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"
INPUT_FILE = "weekly_report.json"


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: environment variable '{name}' is not set.", file=sys.stderr)
        sys.exit(1)
    return value


def notion_request(method: str, path: str, token: str, body: dict | None = None) -> dict:
    url = f"{NOTION_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8")
        print(f"ERROR: Notion API {method} {path} → {e.code}: {body_text}", file=sys.stderr)
        sys.exit(1)


# ── Block builders ────────────────────────────────────────────────────────────

def heading2(text: str) -> dict:
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]}}

def heading3(text: str) -> dict:
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": text}}]}}

def paragraph(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": text or "—"}}]}}

def bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]}}

def divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}

def callout(text: str, emoji: str = "📌") -> dict:
    return {
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
            "icon": {"type": "emoji", "emoji": emoji},
        },
    }

def table_row(cells: list[str]) -> dict:
    return {
        "object": "block", "type": "table_row",
        "table_row": {"cells": [[{"type": "text", "text": {"content": c}}] for c in cells]},
    }

def table_block(header: list[str], rows: list[list[str]]) -> dict:
    """Returns a table block with children. Notion requires table + table_row children."""
    children = [table_row(header)] + [table_row(r) for r in rows]
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": len(header),
            "has_column_header": True,
            "has_row_header": False,
            "children": children,
        },
    }


# ── Report → blocks ───────────────────────────────────────────────────────────

def build_blocks(report: dict) -> list[dict]:
    blocks = []

    # Portfolio snapshot
    nav = report.get("portfolio_nav", 0)
    cash = report.get("cash_available", 0)
    holdings = report.get("holdings_value", nav - cash)
    week_ret = report.get("week_return_pct")
    vs_sp500 = report.get("vs_sp500_week_pct")

    snapshot_lines = [
        f"NAV: ${nav:,.2f}  |  Holdings: ${holdings:,.2f}  |  Cash: ${cash:,.2f}",
    ]
    if week_ret is not None:
        snapshot_lines.append(f"Week return: {week_ret:+.2f}%")
    if vs_sp500 is not None:
        snapshot_lines.append(f"vs S&P 500: {vs_sp500:+.2f}%")

    blocks += [
        callout("  ".join(snapshot_lines), "💼"),
        divider(),
    ]

    # Market context
    if report.get("market_summary"):
        blocks += [heading2("Market Context"), paragraph(report["market_summary"])]
        if report.get("macro_themes"):
            blocks.append(paragraph(report["macro_themes"]))
        blocks.append(divider())

    # Portfolio health
    if report.get("portfolio_health"):
        blocks += [heading2("Portfolio Health"), paragraph(report["portfolio_health"]), divider()]

    # Position review table
    positions = report.get("positions", [])
    if positions:
        blocks.append(heading2("Position Review"))
        header = ["Symbol", "Market Value", "Unrealized P&L", "WHT", "Action", "Rationale"]
        rows = []
        for p in positions:
            pnl = p.get("unrealized_pnl_pct")
            pnl_str = f"{pnl:+.1f}%" if pnl is not None else "—"
            rows.append([
                p.get("symbol", ""),
                f"${p.get('market_value', 0):,.0f}",
                pnl_str,
                p.get("wht_exposure", "—"),
                p.get("action", "—"),
                p.get("rationale", ""),
            ])
        blocks.append(table_block(header, rows))
        blocks.append(divider())

    # Rebalancing
    if report.get("rebalancing"):
        blocks += [heading2("Rebalancing Assessment"), paragraph(report["rebalancing"])]

    # Cash strategy
    if report.get("cash_strategy"):
        blocks += [heading2("Cash Strategy"), paragraph(report["cash_strategy"]), divider()]

    # New opportunities
    opportunities = report.get("new_opportunities", [])
    if opportunities:
        blocks.append(heading2("New Opportunities"))
        for opp in opportunities:
            symbol = opp.get("symbol", "")
            size = opp.get("suggested_size", "")
            rationale = opp.get("rationale", "")
            label = f"{symbol} ({size}): {rationale}" if size else f"{symbol}: {rationale}"
            blocks.append(bullet(label))
        blocks.append(divider())

    # Action items
    action_items = report.get("action_items", [])
    if action_items:
        blocks.append(heading2("Action Items"))
        for item in action_items:
            blocks.append(bullet(item))

    return blocks


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = get_env("NOTION_TOKEN")
    database_id = get_env("NOTION_DATABASE_ID")

    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: {INPUT_FILE} not found in current directory.", file=sys.stderr)
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        report = json.load(f)

    report_date = report.get("report_date", "Unknown date")
    page_title = f"Weekly Report — {report_date}"
    print(f"Creating Notion page: {page_title}")

    blocks = build_blocks(report)

    # Notion API limits children to 100 blocks per request — split if needed
    MAX_BLOCKS_PER_REQUEST = 100

    # Fetch database schema to find the actual title property name
    db = notion_request("GET", f"/databases/{database_id}", token)
    title_prop_name = "Name"  # fallback
    for prop_name, prop_def in db.get("properties", {}).items():
        if prop_def.get("type") == "title":
            title_prop_name = prop_name
            break
    print(f"Title property name: {title_prop_name}")

    # Build page properties — mirrors "Create a database page1" node fields:
    # title, Date (date), NAV (rich_text), Week Change % (rich_text)
    nav_str = f"${report.get('portfolio_nav', 0):,.2f}"

    week_ret = report.get("week_return_pct")
    week_change_str = f"{week_ret:+.2f}%" if week_ret is not None else "N/A"

    properties = {
        title_prop_name: {
            "title": [{"type": "text", "text": {"content": page_title}}]
        },
        "Date": {
            "date": {"start": report_date}
        },
        "NAV": {
            "rich_text": [{"type": "text", "text": {"content": nav_str}}]
        },
        "Week Change %": {
            "rich_text": [{"type": "text", "text": {"content": week_change_str}}]
        },
    }

    # Create the page with the first batch of blocks
    first_batch = blocks[:MAX_BLOCKS_PER_REQUEST]
    page = notion_request(
        "POST",
        "/pages",
        token,
        {
            "parent": {"database_id": database_id},
            "properties": properties,
            "children": first_batch,
        },
    )

    page_id = page["id"]
    print(f"Page created: {page_id}")

    # Append remaining blocks in batches
    remaining = blocks[MAX_BLOCKS_PER_REQUEST:]
    batch_num = 2
    while remaining:
        batch = remaining[:MAX_BLOCKS_PER_REQUEST]
        remaining = remaining[MAX_BLOCKS_PER_REQUEST:]
        notion_request(
            "PATCH",
            f"/blocks/{page_id}/children",
            token,
            {"children": batch},
        )
        print(f"Appended block batch {batch_num}")
        batch_num += 1

    page_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")
    print(f"\nDone. Report published: {page_url}")


if __name__ == "__main__":
    main()
