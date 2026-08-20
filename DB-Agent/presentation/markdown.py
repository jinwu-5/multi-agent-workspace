from typing import Any, Dict, List
from collections import Counter
from datetime import date, datetime
from decimal import Decimal

def to_markdown_table(columns: List[str], rows: List[Dict[str, Any]], max_width: int = 60) -> str:
    if not columns:
        return "(no columns)"
    def fmt(v: Any) -> str:
        s = "" if v is None else str(v)
        return (s[:max_width] + "…") if len(s) > max_width else s
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, sep]
    for row in rows:
        lines.append("| " + " | ".join(fmt(row.get(c)) for c in columns) + " |")
    return "\n".join(lines)

def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal))

def _is_date(v: Any) -> bool:
    return isinstance(v, (date, datetime))

def insight_bullets(columns: List[str], rows: List[Dict[str, Any]]) -> List[str]:
    bullets = [f"Rows returned: {len(rows)} · Columns: {len(columns)}"]
    if not rows or not columns:
        return bullets
    if "title" in columns:
        titles = [r.get("title") for r in rows if r.get("title")]
        bullets.append(f"Distinct titles in result: {len(set(titles))}")
    if "release_year" in columns:
        yrs = [r.get("release_year") for r in rows if _is_num(r.get("release_year"))]
        if yrs:
            bullets.append(f"Release year range (result set): {min(yrs)}–{max(yrs)}")
    for dcol in ["date_added", "created_at", "added_at", "premiere_date"]:
        if dcol in columns:
            ds = [r.get(dcol) for r in rows if _is_date(r.get(dcol))]
            if ds:
                bullets.append(f"{dcol} range (result set): {min(ds)} → {max(ds)}")
            break
    for cat in ["type", "genre", "rating"]:
        if cat in columns:
            vals = [r.get(cat) for r in rows if r.get(cat)]
            if vals:
                top = ", ".join(f"{v} ({n})" for v, n in Counter(vals).most_common(3))
                bullets.append(f"Top {cat} values (result set): {top}")
            break
    return bullets

def render_markdown_result(sql: str, columns: List[str], rows: List[Dict[str, Any]]) -> str:
    md_sql = f"## SQL\n\n```sql\n{sql}\n```\n"
    md_table = "## Result\n\n" + (to_markdown_table(columns, rows) if rows else "_No rows returned._")
    insights = insight_bullets(columns, rows)
    md_insights = "\n\n## Insights\n\n" + "\n".join(f"- {b}" for b in insights)
    return md_sql + "\n" + md_table + md_insights + "\n"