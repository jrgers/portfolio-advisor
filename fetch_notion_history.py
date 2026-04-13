"""
Fetch the last N weekly portfolio reports from Notion and save as notion_history.json.

Environment variables required:
    NOTION_TOKEN         — Notion integration token (secret)
    NOTION_DATABASE_ID   — ID of the Weekly Reports database
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


def fetch_page_text(page_id: str, token: str) -> str:
    """Fetch all block content from a page and return as plain text."""
    blocks = []
    cursor = None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        result = notion_request("GET", path, token)
        blocks.extend(result.get("results", []))
        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")

    lines = []
    for block in blocks:
        btype = block.get("type", "")
        content = block.get(btype, {})
        rich = content.get("rich_text", [])
        text = "".join(r.get("plain_text", "") for r in rich)
        if text:
            lines.append(text)

    return "\n".join(lines)


def main():
    token = get_env("NOTION_TOKEN")
    database_id = get_env("NOTION_DATABASE_ID")
    count = int(get_env("NOTION_HISTORY_COUNT", "4"))

    print(f"Querying Notion database {database_id} for last {count} reports...")

    result = notion_request(
        "POST",
        f"/databases/{database_id}/query",
        token,
        {
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": count,
        },
    )

    pages = result.get("results", [])
    print(f"Found {len(pages)} report(s).")

    history = []
    for page in pages:
        page_id = page["id"]
        props = page.get("properties", {})

        # Extract title — look for a property of type title
        title = ""
        for prop in props.values():
            if prop.get("type") == "title":
                rich = prop.get("title", [])
                title = "".join(r.get("plain_text", "") for r in rich)
                break

        created = page.get("created_time", "")[:10]  # YYYY-MM-DD

        print(f"  Fetching page: {title or page_id} ({created})")
        content = fetch_page_text(page_id, token)

        history.append({
            "date": created,
            "title": title,
            "content": content,
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(history)} report(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
