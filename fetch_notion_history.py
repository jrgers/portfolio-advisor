"""
Fetch the last N weekly portfolio reports from Notion and save as notion_history.json.

Mirrors the "Get a database page" + "HTTP Request3" nodes in Portfolio Advisor v2:
- Queries the Weekly Reports database sorted by created_time descending
- For each page, fetches its block children (the report content)
- Extracts properties: title, Date, NAV, Week Change %

Environment variables required:
    NOTION_TOKEN         — Notion integration token (secret)
    NOTION_DATABASE_ID   — Weekly Reports database ID
                           (731dec98-92e8-465b-960d-16b565e32033)
    NOTION_HISTORY_COUNT — Number of past reports to fetch (default: 4)
"""

import json
import os
import sys
import urllib.request
import urllib.error

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"
OUTPUT_FILE = "notion_history.json"


def get_env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
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


def extract_rich_text(prop: dict) -> str:
    """Extract plain text from a rich_text or title property."""
    rich = prop.get("rich_text") or prop.get("title") or []
    return "".join(r.get("plain_text", "") for r in rich)


def extract_properties(props: dict) -> dict:
    """Extract the known database properties from a page."""
    result = {}

    for key, prop in props.items():
        ptype = prop.get("type")

        if ptype == "title":
            result["title"] = extract_rich_text(prop)

        elif ptype == "rich_text":
            # NAV, Week Change %, or any other rich_text field
            result[key] = extract_rich_text(prop)

        elif ptype == "date":
            date_val = prop.get("date") or {}
            result[key] = date_val.get("start", "")

    return result


def fetch_page_blocks(page_id: str, token: str) -> str:
    """
    Fetch all block children for a page and return as plain text.
    Mirrors n8n's HTTP Request3: GET /blocks/{id}/children?page_size=100
    """
    lines = []
    cursor = None

    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"

        result = notion_request("GET", path, token)

        for block in result.get("results", []):
            btype = block.get("type", "")
            content = block.get(btype, {})
            rich = content.get("rich_text", [])
            text = "".join(r.get("plain_text", "") for r in rich)
            if text:
                lines.append(text)

        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")

    return "\n".join(lines)


def main():
    token = get_env("NOTION_TOKEN")
    database_id = get_env("NOTION_DATABASE_ID")
    count = int(get_env("NOTION_HISTORY_COUNT", "4"))

    print(f"Querying Notion database {database_id} for last {count} report(s)...")

    # Mirror "Get a database page" node: getAll, sort created_time desc, limit N
    result = notion_request(
        "POST",
        f"/databases/{database_id}/query",
        token,
        {
            "sorts": [
                {
                    "timestamp": "created_time",
                    "direction": "descending",
                }
            ],
            "page_size": count,
        },
    )

    pages = result.get("results", [])
    print(f"Found {len(pages)} report(s).")

    history = []
    for page in pages:
        page_id = page["id"]
        created = page.get("created_time", "")[:10]  # YYYY-MM-DD

        # Extract structured properties (title, Date, NAV, Week Change %)
        props = extract_properties(page.get("properties", {}))
        title = props.get("title", f"Report {created}")

        print(f"  Fetching blocks for: {title} ({created})")

        # Mirror HTTP Request3: GET /blocks/{page.id}/children?page_size=100
        content = fetch_page_blocks(page_id, token)

        history.append({
            "title": title,
            "date": props.get("Date", created),
            "nav": props.get("NAV", ""),
            "week_change": props.get("Week Change %", ""),
            "created_time": created,
            "content": content,
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(history)} report(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
