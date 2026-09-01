"""הפקת דוחות HTML אינטראקטיביים ולוח בקרה ויזואלי עבור SBpy.

יוצר קובץ HTML עצמאי ויפהפה (ללא תלויות חיצוניות וללא צורך ברשת)
הכולל מדד בריאות פרויקט, גרפים ודיאגרמות, וטבלת ממצאים הניתנת לסינון ולחיפוש.
"""

from __future__ import annotations

import html
import os
import time

from .results import Finding, ScanResult


def _compute_grade(findings: list[Finding]) -> tuple[str, str]:
    """מחשב ציון בריאות לפרויקט (A/B/C/D) וצבע מתאים."""
    criticals = sum(1 for f in findings if f.severity == "critical")
    errors = sum(1 for f in findings if f.severity == "error")
    warns = sum(1 for f in findings if f.severity == "warn")

    if criticals == 0 and errors == 0 and warns <= 3:
        return "A", "#10b981"  # ירוק
    elif criticals == 0 and errors <= 3:
        return "B", "#3b82f6"  # כחול
    elif criticals <= 1 and errors <= 8:
        return "C", "#f59e0b"  # כתום
    return "D", "#ef4444"      # אדום


def generate_html_report(
    results: list[ScanResult],
    *,
    project_root: str = ".",
    output_path: str = "sbpy_report.html",
) -> str:
    """יוצר דוח HTML עצמאי ומרהיב של כל ממצאי הסריקה בפרויקט."""
    all_findings: list[Finding] = []
    for r in results:
        all_findings.extend(r.findings)

    grade, grade_color = _compute_grade(all_findings)
    total_issues = len(all_findings)
    sec_count = sum(1 for f in all_findings if f.severity in ("critical", "error") or "sec" in f.rule)
    opt_count = sum(1 for f in all_findings if "loop" in f.rule or "len" in f.rule or "re-compile" in f.rule)
    mod_count = sum(1 for f in all_findings if "pathlib" in f.rule or "type" in f.rule)

    findings_rows = []
    for f in all_findings:
        sev_badge = {
            "critical": '<span class="badge badge-critical">Critical</span>',
            "error": '<span class="badge badge-error">Error</span>',
            "warn": '<span class="badge badge-warn">Warning</span>',
            "info": '<span class="badge badge-info">Info</span>',
        }.get(f.severity, f'<span class="badge">{f.severity}</span>')

        if f.file:
            try:
                file_display = os.path.relpath(f.file, project_root)
            except ValueError:
                file_display = f.file
        else:
            file_display = "<code>"
        hint_html = f'<div class="hint">💡 {html.escape(f.hint)}</div>' if f.hint else ""

        findings_rows.append(
            f"""
            <tr data-severity="{html.escape(f.severity)}" data-rule="{html.escape(f.rule)}">
                <td>{sev_badge}</td>
                <td><code class="rule-code">{html.escape(f.rule)}</code></td>
                <td><strong>{html.escape(file_display)}:{f.line}</strong></td>
                <td>
                    <div class="message">{html.escape(f.message)}</div>
                    {hint_html}
                </td>
            </tr>
            """
        )

    table_body = "\n".join(findings_rows) if findings_rows else '<tr><td colspan="4" class="empty">🎉 לא נמצאו שגיאות או בעיות! הפרויקט נקי לחלוטין.</td></tr>'

    html_content = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SBpy דוח בריאות פרויקט</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --card-border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #38bdf8;
            --accent: #818cf8;
            --critical: #ef4444;
            --error: #f87171;
            --warn: #fbbf24;
            --info: #38bdf8;
            --success: #34d399;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        body {{ background: var(--bg); color: var(--text-main); line-height: 1.6; padding: 2rem; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--card-border); padding-bottom: 1.5rem; margin-bottom: 2rem; }}
        .title {{ font-size: 1.8rem; font-weight: 800; background: linear-gradient(135deg, var(--primary), var(--accent)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .meta {{ color: var(--text-muted); font-size: 0.9rem; }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }}
        .card {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 1.5rem; display: flex; flex-direction: column; justify-content: center; position: relative; overflow: hidden; }}
        .card-val {{ font-size: 2.2rem; font-weight: 800; margin-top: 0.5rem; }}
        .card-lbl {{ color: var(--text-muted); font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }}
        .grade-badge {{ font-size: 3rem; font-weight: 900; color: {grade_color}; }}

        .search-bar {{ margin-bottom: 1.5rem; display: flex; gap: 1rem; }}
        .search-input {{ flex: 1; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 0.75rem 1rem; color: var(--text-main); font-size: 1rem; outline: none; }}
        .search-input:focus {{ border-color: var(--primary); }}

        table {{ width: 100%; border-collapse: collapse; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; overflow: hidden; }}
        th, td {{ padding: 1rem; text-align: right; border-bottom: 1px solid var(--card-border); }}
        th {{ background: #182234; color: var(--text-muted); font-weight: 600; font-size: 0.85rem; text-transform: uppercase; }}
        tr:hover {{ background: #243248; }}
        .empty {{ text-align: center; padding: 3rem; color: var(--success); font-size: 1.2rem; }}

        .badge {{ padding: 0.25rem 0.6rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 700; display: inline-block; }}
        .badge-critical {{ background: rgba(239, 68, 68, 0.2); color: var(--critical); border: 1px solid var(--critical); }}
        .badge-error {{ background: rgba(248, 113, 113, 0.2); color: var(--error); border: 1px solid var(--error); }}
        .badge-warn {{ background: rgba(251, 191, 36, 0.2); color: var(--warn); border: 1px solid var(--warn); }}
        .badge-info {{ background: rgba(56, 189, 248, 0.2); color: var(--info); border: 1px solid var(--info); }}
        .rule-code {{ color: var(--primary); background: #0f172a; padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.85rem; }}
        .hint {{ margin-top: 0.4rem; color: var(--text-muted); font-size: 0.85rem; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <div class="title">⚡ SBpy · דוח בריאות פרויקט</div>
                <div class="meta">נוצר ב: {time.strftime('%Y-%m-%d %H:%M:%S')} | נתיב: {html.escape(os.path.abspath(project_root))}</div>
            </div>
            <div>
                <span class="card-lbl">ציון בריאות</span>
                <div class="grade-badge">{grade}</div>
            </div>
        </header>

        <div class="grid">
            <div class="card">
                <span class="card-lbl">סה"כ ממצאים</span>
                <span class="card-val" style="color: var(--text-main);">{total_issues}</span>
            </div>
            <div class="card">
                <span class="card-lbl">אבטחה ובטיחות</span>
                <span class="card-val" style="color: var(--critical);">{sec_count}</span>
            </div>
            <div class="card">
                <span class="card-lbl">הזדמנויות ביצועים</span>
                <span class="card-val" style="color: var(--warn);">{opt_count}</span>
            </div>
            <div class="card">
                <span class="card-lbl">שדרוג מודרני (@MOD)</span>
                <span class="card-val" style="color: var(--primary);">{mod_count}</span>
            </div>
        </div>

        <div class="search-bar">
            <input type="text" id="filterInput" class="search-input" placeholder="🔍 סינון לפי חוק, קובץ, או תיאור..." onkeyup="filterTable()">
        </div>

        <table>
            <thead>
                <tr>
                    <th style="width: 120px;">חומרה</th>
                    <th style="width: 220px;">חוק</th>
                    <th style="width: 250px;">מיקום</th>
                    <th>תיאור והצעה</th>
                </tr>
            </thead>
            <tbody id="findingsTable">
                {table_body}
            </tbody>
        </table>
    </div>

    <script>
        function filterTable() {{
            const input = document.getElementById('filterInput').value.toLowerCase();
            const rows = document.querySelectorAll('#findingsTable tr');
            rows.forEach(row => {{
                const text = row.innerText.toLowerCase();
                row.style.display = text.includes(input) ? '' : 'none';
            }});
        }}
    </script>
</body>
</html>
"""
    abs_out = os.path.abspath(output_path)
    with open(abs_out, "w", encoding="utf-8") as handle:
        handle.write(html_content)
    return abs_out
