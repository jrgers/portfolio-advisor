"""
Fetch IBKR portfolio data via Flex Web Service and save to ibkr_portfolio.xml.

Environment variables required:
    IBKR_FLEX_TOKEN      — Flex Web Service token
    IBKR_FLEX_QUERY_ID   — Flex Query ID
    IBKR_FLEX_BASE_URL   — Base URL (e.g. https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService)
    IBKR_FLEX_VERSION    — Flex version (e.g. 3)
"""

import os
import sys
import time
import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse

OUTPUT_FILE = "ibkr_portfolio.xml"
POLL_INTERVAL = 5   # seconds between /GetStatement retries
MAX_RETRIES = 12    # ~60 seconds total wait


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: environment variable '{name}' is not set.", file=sys.stderr)
        sys.exit(1)
    return value


def fetch_url(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


def send_request(base_url: str, token: str, query_id: str, version: str) -> str:
    """Call /SendRequest and return the reference code."""
    params = urllib.parse.urlencode({
        "t": token,
        "q": query_id,
        "v": version,
    })
    url = f"{base_url}/SendRequest?{params}"
    print(f"Sending request: {url}")
    body = fetch_url(url)
    print(f"SendRequest response:\n{body}\n")

    root = ET.fromstring(body)
    status = root.findtext("Status")

    if status == "Success":
        ref_code = root.findtext("ReferenceCode")
        if not ref_code:
            print("ERROR: SendRequest succeeded but no ReferenceCode found.", file=sys.stderr)
            sys.exit(1)
        return ref_code

    error_msg = root.findtext("ErrorMessage") or "(no message)"
    print(f"ERROR: SendRequest failed — Status={status}, Message={error_msg}", file=sys.stderr)
    sys.exit(1)


def get_statement(base_url: str, token: str, ref_code: str, version: str) -> str:
    """Poll /GetStatement until the statement is ready, then return the XML body."""
    params = urllib.parse.urlencode({
        "t": token,
        "q": ref_code,
        "v": version,
    })
    url = f"{base_url}/GetStatement?{params}"

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"Polling GetStatement (attempt {attempt}/{MAX_RETRIES}): {url}")
        body = fetch_url(url)

        # IBKR returns plain XML if ready, or a status envelope if still processing
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            print("ERROR: Could not parse GetStatement response as XML.", file=sys.stderr)
            print(body, file=sys.stderr)
            sys.exit(1)

        # Status envelope tags used by IBKR
        status = root.findtext("Status")
        if status is None:
            # Root tag is FlexQueryResponse — statement is ready
            return body

        if status == "Success":
            return body

        if status in ("Warn", "Processing"):
            error_msg = root.findtext("ErrorMessage") or ""
            print(f"  Status={status}: {error_msg} — waiting {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)
            continue

        error_msg = root.findtext("ErrorMessage") or "(no message)"
        print(f"ERROR: GetStatement failed — Status={status}, Message={error_msg}", file=sys.stderr)
        sys.exit(1)

    print("ERROR: Timed out waiting for IBKR statement.", file=sys.stderr)
    sys.exit(1)


def main():
    token    = get_env("IBKR_FLEX_TOKEN")
    query_id = get_env("IBKR_FLEX_QUERY_ID")
    base_url = get_env("IBKR_FLEX_BASE_URL").rstrip("/")
    version  = get_env("IBKR_FLEX_VERSION")

    ref_code = send_request(base_url, token, query_id, version)
    print(f"Reference code: {ref_code}")

    xml_body = get_statement(base_url, token, ref_code, version)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_body)

    print(f"\nSaved to {OUTPUT_FILE} ({len(xml_body):,} bytes)")


if __name__ == "__main__":
    main()
