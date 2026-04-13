"""
Send the weekly portfolio report as an HTML email via SendGrid.

Reads weekly_report.json from the current directory and sends a formatted
HTML email matching the Portfolio Advisor v2 style.

Environment variables required:
    SENDGRID_API_KEY   — SendGrid API key (secret)
    EMAIL_FROM         — Sender address (default: johnnygerges@gmail.com)
    EMAIL_TO           — Recipient address (default: johnnygerges@gmail.com)
    EMAIL_FROM_NAME    — Sender display name (default: Johny Gerges)
"""

import json
import os
import sys
import urllib.request
import urllib.error

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"
INPUT_FILE = "weekly_report.json"


def get_env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        print(f"ERROR: environment variable '{name}' is not set.", file=sys.stderr)
        sys.exit(1)
    return value


def esc(text: str) -> str:
    """Escape HTML special characters."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def pnl_color(value: float | None) -> str:
    if value is None:
        return "#6c757d"
    return "#28a745" if value >= 0 else "#dc3545"


def action_color(action: str) -> str:
    a = action.upper()
    if "EXIT" in a:
        return "#dc3545"
    if "REDUCE" in a:
        return "#fd7e14"
    if "ADD" in a:
        return "#28a745"
    return "#6c757d"


def build_html(report: dict) -> str:
    date = report.get("report_date", "")
    nav = report.get("portfolio_nav", 0)
    cash = report.get("cash_available", 0)
    holdings = report.get("holdings_value", nav - cash)
    week_ret = report.get("week_return_pct")
    vs_sp500 = report.get("vs_sp500_week_pct")

    week_ret_str = f"{week_ret:+.2f}%" if week_ret is not None else "N/A"
    vs_sp500_str = f"{vs_sp500:+.2f}%" if vs_sp500 is not None else "N/A"
    week_color = pnl_color(week_ret)

    # Position rows
    position_rows = ""
    for p in report.get("positions", []):
        pnl = p.get("unrealized_pnl_pct")
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else "—"
        action = p.get("action", "HOLD")
        ac = action_color(action)
        position_rows += f"""
        <tr>
          <td style='padding:8px 10px;font-weight:bold'>{esc(p.get('symbol',''))}</td>
          <td style='padding:8px 10px;text-align:right'>${p.get('market_value',0):,.0f}</td>
          <td style='padding:8px 10px;text-align:right;color:{pnl_color(pnl)}'>{esc(pnl_str)}</td>
          <td style='padding:8px 10px;text-align:center'>{esc(p.get('wht_exposure','—'))}</td>
          <td style='padding:8px 10px;text-align:center'>
            <span style='background:{ac};color:#fff;padding:2px 8px;border-radius:3px;font-size:11px'>{esc(action)}</span>
          </td>
          <td style='padding:8px 10px;font-size:12px;color:#555'>{esc(p.get('rationale',''))}</td>
        </tr>"""

    # Action items
    action_items_html = "".join(
        f"<li style='padding:4px 0'>{esc(item)}</li>"
        for item in report.get("action_items", [])
    )

    # New opportunities
    opportunities_html = "".join(
        f"<li style='padding:4px 0'><strong>{esc(o.get('symbol',''))}</strong> ({esc(o.get('suggested_size',''))}) — {esc(o.get('rationale',''))}</li>"
        for o in report.get("new_opportunities", [])
    )

    def section(title: str, content: str) -> str:
        return f"""
        <div style='margin-bottom:24px'>
          <h2 style='font-size:15px;font-weight:600;color:#1a1a1a;border-bottom:2px solid #e9ecef;padding-bottom:6px;margin-bottom:12px'>{esc(title)}</h2>
          {content}
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset='utf-8'></head>
<body style='margin:0;padding:0;background:#f4f6f9;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif'>
  <div style='max-width:800px;margin:24px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)'>

    <!-- Header -->
    <div style='background:#1a1a2e;padding:20px 30px;color:#fff'>
      <h1 style='margin:0;font-size:20px;font-weight:600'>Portfolio Advisory — {esc(date)}</h1>
      <div style='margin-top:8px;font-size:13px;color:#adb5bd'>
        NAV: <strong>${nav:,.2f}</strong> &nbsp;|&nbsp;
        Holdings: <strong>${holdings:,.2f}</strong> &nbsp;|&nbsp;
        Cash: <strong>${cash:,.2f}</strong> &nbsp;|&nbsp;
        Week: <strong style='color:{week_color}'>{esc(week_ret_str)}</strong> &nbsp;|&nbsp;
        vs S&amp;P 500: <strong>{esc(vs_sp500_str)}</strong>
      </div>
    </div>

    <!-- Body -->
    <div style='padding:24px 30px'>

      {section('Market Context',
        f"<p style='color:#333;font-size:13px;line-height:1.6'>{esc(report.get('market_summary',''))}</p>"
        + (f"<p style='color:#555;font-size:13px;line-height:1.6'>{esc(report.get('macro_themes',''))}</p>" if report.get('macro_themes') else '')
      )}

      {section('Portfolio Health',
        f"<p style='color:#333;font-size:13px;line-height:1.6'>{esc(report.get('portfolio_health',''))}</p>"
      ) if report.get('portfolio_health') else ''}

      {section('Position Review', f"""
        <table style='width:100%;border-collapse:collapse;font-size:13px'>
          <tr style='background:#f8f9fa'>
            <th style='padding:8px 10px;text-align:left'>Symbol</th>
            <th style='padding:8px 10px;text-align:right'>Value</th>
            <th style='padding:8px 10px;text-align:right'>P&amp;L %</th>
            <th style='padding:8px 10px;text-align:center'>WHT</th>
            <th style='padding:8px 10px;text-align:center'>Action</th>
            <th style='padding:8px 10px;text-align:left'>Rationale</th>
          </tr>
          {position_rows}
        </table>
      """) if position_rows else ''}

      {section('Rebalancing',
        f"<p style='color:#333;font-size:13px;line-height:1.6'>{esc(report.get('rebalancing',''))}</p>"
      ) if report.get('rebalancing') else ''}

      {section('Cash Strategy',
        f"<p style='color:#333;font-size:13px;line-height:1.6'>{esc(report.get('cash_strategy',''))}</p>"
      ) if report.get('cash_strategy') else ''}

      {section('New Opportunities',
        f"<ul style='margin:0;padding-left:20px;color:#333;font-size:13px'>{opportunities_html}</ul>"
      ) if opportunities_html else ''}

      {section('Action Items',
        f"<ul style='margin:0;padding-left:20px;color:#333;font-size:13px'>{action_items_html}</ul>"
      ) if action_items_html else ''}

    </div>

    <!-- Footer -->
    <div style='background:#f8f9fa;padding:12px 30px;font-size:11px;color:#888;border-top:1px solid #e9ecef'>
      Generated {esc(date)} | Portfolio Advisor | Advisory only — does not execute trades
    </div>

  </div>
</body>
</html>"""

    return html


def main():
    api_key = get_env("SENDGRID_API_KEY")
    from_email = get_env("EMAIL_FROM", "johnnygerges@gmail.com")
    from_name = get_env("EMAIL_FROM_NAME", "Johny Gerges")
    to_email = get_env("EMAIL_TO", "johnnygerges@gmail.com")

    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: {INPUT_FILE} not found in current directory.", file=sys.stderr)
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        report = json.load(f)

    report_date = report.get("report_date", "")
    subject = f"Portfolio Advisory — {report_date}"
    html = build_html(report)

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": from_name},
        "subject": subject,
        "content": [{"type": "text/html", "value": html}],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SENDGRID_API_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"Email sent — status {resp.status}: {subject}")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8")
        print(f"ERROR: SendGrid {e.code}: {body_text}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
