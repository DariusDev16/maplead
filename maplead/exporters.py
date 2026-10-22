"""
Exporters: csv, tsv, json, xlsx, txt, html.

The XLSX writer is hand-rolled on top of zipfile + XML (no openpyxl needed),
so the tool stays dependency-free. Output opens in Excel / LibreOffice /
Google Sheets / Numbers.
"""

from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence, Tuple
from xml.sax.saxutils import escape as _xesc

FORMATS: Tuple[Tuple[str, str, str], ...] = (
    ("csv", "CSV", "Universal - Excel, Sheets, CRM import"),
    ("xlsx", "Excel", "Formatted .xlsx workbook with a meta sheet"),
    ("json", "JSON", "Full-fidelity, keeps types & arrays"),
    ("txt", "Text", "Human readable lead list"),
    ("tsv", "TSV", "Tab separated, pastes into Sheets"),
    ("html", "HTML", "Styled report you can open/print"),
)

EXT = {"csv": "csv", "tsv": "tsv", "json": "json", "xlsx": "xlsx", "txt": "txt", "html": "html"}
LABEL = {k: lab for k, lab, _ in FORMATS}
DESC = {k: d for k, _, d in FORMATS}


def build_columns(fields: Sequence[str], leads: Sequence[Dict[str, Any]],
                  include_extra: bool = False) -> List[str]:
    """Requested fields, in the requested order.

    include_extra=True (the user asked for "everything") also appends any
    additional keys the API happened to return.
    """
    cols: List[str] = []
    for f in fields:
        if f not in cols:
            cols.append(f)
    if include_extra:
        for lead in leads:
            for k in lead:
                if k not in cols and k not in ("_query", "_source", "_scraped_at"):
                    cols.append(k)
    return cols


def _fmt(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return " | ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


# --------------------------------------------------------------------------- #
# csv / tsv
# --------------------------------------------------------------------------- #

def export_csv(path: str, leads: Sequence[Dict[str, Any]], columns: Sequence[str],
               meta: Dict[str, Any] | None = None, delimiter: str = ",") -> Dict[str, Any]:
    with open(path, "w", newline="", encoding="utf-8-sig" if delimiter == "," else "utf-8") as fh:
        w = csv.writer(fh, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        w.writerow(columns)
        for lead in leads:
            w.writerow([_fmt(lead.get(c)) for c in columns])
    return {"rows": len(leads), "columns": len(columns)}


# --------------------------------------------------------------------------- #
# json
# --------------------------------------------------------------------------- #

def export_json(path: str, leads: Sequence[Dict[str, Any]], columns: Sequence[str],
                meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = {
        "meta": meta or {},
        "columns": list(columns),
        "count": len(leads),
        "leads": [{c: lead.get(c) for c in columns} for lead in leads],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return {"rows": len(leads), "columns": len(columns)}


# --------------------------------------------------------------------------- #
# txt
# --------------------------------------------------------------------------- #

def export_txt(path: str, leads: Sequence[Dict[str, Any]], columns: Sequence[str],
               meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    lines: List[str] = []
    title = (meta or {}).get("query", "Google Maps leads")
    lines.append("=" * 78)
    lines.append(title.upper())
    lines.append("=" * 78)
    if meta:
        for k in ("location", "provider", "generated_at"):
            if meta.get(k):
                lines.append(f"{k:<14}: {meta[k]}")
    lines.append(f"{'leads':<14}: {len(leads)}")
    lines.append("")
    for i, lead in enumerate(leads, 1):
        lines.append(f"[{i:>3}] {lead.get('name', '')}")
        for c in columns:
            if c in ("name", "category"):
                continue
            val = _fmt(lead.get(c))
            if val == "":
                continue
            text = str(val)
            if len(text) > 96:
                text = text[:93] + "..."
            lines.append(f"      {c.replace('_', ' '):<16}: {text}")
        lines.append("-" * 78)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return {"rows": len(leads), "columns": len(columns)}


# --------------------------------------------------------------------------- #
# html
# --------------------------------------------------------------------------- #

_HTML_TMPL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; padding:32px; background:#0b1120; color:#e2e8f0;
         font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  h1 {{ font-size:22px; margin:0 0 4px; letter-spacing:-.4px; }}
  .sub {{ color:#64748b; margin-bottom:20px; }}
  .chips span {{ display:inline-block; background:#1e293b; border:1px solid #334155;
                 border-radius:999px; padding:3px 12px; margin:0 6px 6px 0; font-size:12px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th {{ position:sticky; top:0; background:#111c33; text-align:left; padding:9px 10px;
        border-bottom:1px solid #334155; color:#7dd3fc; font-weight:600; white-space:nowrap; }}
  td {{ padding:8px 10px; border-bottom:1px solid #1e293b; vertical-align:top; }}
  tr:hover td {{ background:#132038; }}
  a {{ color:#7dd3fc; text-decoration:none; }}
  .rating {{ color:#fbbf24; }}
</style></head><body>
<h1>{title}</h1>
<div class="sub">{subtitle}</div>
<div class="chips">{chips}</div>
<table><thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table>
</body></html>
"""


def export_html(path: str, leads: Sequence[Dict[str, Any]], columns: Sequence[str],
                meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    meta = meta or {}
    url_cols = {"website", "maps_url", "facebook", "instagram", "linkedin", "logo_url"}
    rate_cols = {"rating", "reviews"}

    def cell(lead: Dict[str, Any], col: str) -> str:
        val = _fmt(lead.get(col))
        if val == "":
            return "<td></td>"
        text = str(val)
        if col in url_cols and text.startswith("http"):
            label = text.split("//", 1)[-1][:46]
            return f'<td><a href="{_xesc(text)}" target="_blank" rel="noopener">{_xesc(label)}</a></td>'
        if col == "rating":
            return f'<td class="rating">{"★" * int(float(val or 0))} {val}</td>'
        if col in rate_cols:
            return f"<td>{_xesc(text)}</td>"
        return f"<td>{_xesc(text)}</td>"

    headers = "".join(f"<th>{_xesc(c.replace('_', ' '))}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(cell(l, c) for c in columns) + "</tr>" for l in leads
    )
    chips = "".join(
        f"<span>{_xesc(k)}: <strong>{_xesc(str(v))}</strong></span>"
        for k, v in list(meta.items())[:8] if v
    )
    html = _HTML_TMPL.format(
        title=_xesc(str(meta.get("query", "Google Maps leads"))),
        subtitle=_xesc(f"{len(leads)} leads - generated {meta.get('generated_at', '')}"),
        chips=chips, headers=headers, body=body,
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return {"rows": len(leads), "columns": len(columns)}


# --------------------------------------------------------------------------- #
# xlsx  (minimal, spec-compliant writer)
# --------------------------------------------------------------------------- #

_XLSX_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _esc(text: Any) -> str:
    s = "" if text is None else str(text)
    s = _CTRL.sub("", s)
    return "".join(_XLSX_ESC.get(ch, ch) for ch in s)


def _col_letter(idx: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA"""
    out = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        out = chr(65 + rem) + out
    return out


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _sheet_xml(rows: Sequence[Sequence[Any]], widths: Sequence[int],
               header_style: int = 1, wrap_style: int = 3,
               freeze: bool = True, autofilter: bool = True) -> str:
    ncols = len(widths)
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
    ]
    if rows:
        parts.append(f'<dimension ref="A1:{_col_letter(ncols - 1)}{len(rows)}"/>')
    if freeze:
        parts.append(
            '<sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>'
        )
    parts.append('<sheetFormatPr defaultRowHeight="15"/>')
    parts.append("<cols>")
    for i, w in enumerate(widths, 1):
        parts.append(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>')
    parts.append("</cols>")
    parts.append("<sheetData>")
    for r, row in enumerate(rows, 1):
        height = ' ht="22" customHeight="1"' if r == 1 and header_style else ""
        parts.append(f'<row r="{r}"{height}>')
        for c, value in enumerate(row):
            ref = f"{_col_letter(c)}{r}"
            style = header_style if (r == 1 and header_style) else (
                wrap_style if isinstance(value, str) and len(value) > 45 else 0)
            if _is_num(value):
                parts.append(f'<c r="{ref}" s="{style}" t="n"><v>{value}</v></c>')
            elif value is None or value == "":
                if style:
                    parts.append(f'<c r="{ref}" s="{style}"/>')
            else:
                parts.append(f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">'
                             f'{_esc(value)}</t></is></c>')
        parts.append("</row>")
    parts.append("</sheetData>")
    if autofilter and rows:
        parts.append(f'<autoFilter ref="A1:{_col_letter(ncols - 1)}{len(rows)}"/>')
    parts.append("</worksheet>")
    return "".join(parts)


_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="3">'
    '<font><sz val="11"/><color theme="1"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>'
    '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>'
    '<font><b/><sz val="13"/><color rgb="FF0B1120"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>'
    '</fonts>'
    '<fills count="3">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FF0EA5E9"/><bgColor indexed="64"/></patternFill></fill>'
    '</fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="4">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"'
    ' applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"'
    '><alignment vertical="top" wrapText="0"/></xf>'
    '</cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>'
)

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '</Types>'
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    '</Relationships>'
)

_WB_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>'
)


def _workbook_xml(sheet1: str, sheet2: str) -> str:
    safe = lambda n: re.sub(r'[\[\]:*?/\\]', "_", n)[:31] or "Sheet"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{safe(sheet1)}" sheetId="1" r:id="rId1"/>'
        f'<sheet name="{safe(sheet2)}" sheetId="2" r:id="rId2"/></sheets>'
        '<calcPr calcId="0"/>'
        '</workbook>'
    )


def export_xlsx(path: str, leads: Sequence[Dict[str, Any]], columns: Sequence[str],
                meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    meta = meta or {}

    header = [c.replace("_", " ").title() for c in columns]
    rows: List[List[Any]] = [header]
    for lead in leads:
        row: List[Any] = []
        for c in columns:
            v = lead.get(c)
            row.append(v if _is_num(v) else _fmt(v))
        rows.append(row)

    widths = []
    for i, h in enumerate(header):
        w = len(str(h)) + 4
        for r in rows[1:400]:
            val = r[i]
            w = max(w, min(len(str(val)) + 2, 52))
        widths.append(min(max(w, 10), 52))

    meta_rows: List[List[Any]] = [["MAPLEAD export", ""]]
    for k, v in meta.items():
        meta_rows.append([str(k).replace("_", " "), _fmt(v)])
    meta_rows.append(["total leads", len(leads)])
    meta_rows.append(["exported at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")])
    meta_widths = [22, 70]

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr("xl/workbook.xml", _workbook_xml("Leads", "Meta"))
        z.writestr("xl/_rels/workbook.xml.rels", _WB_RELS)
        z.writestr("xl/styles.xml", _STYLES)
        z.writestr("xl/worksheets/sheet1.xml",
                   _sheet_xml(rows, widths, header_style=1, wrap_style=3))
        z.writestr("xl/worksheets/sheet2.xml",
                   _sheet_xml(meta_rows, meta_widths, header_style=2, freeze=False, autofilter=False))
    return {"rows": len(leads), "columns": len(columns)}


# --------------------------------------------------------------------------- #
# dispatcher
# --------------------------------------------------------------------------- #

WRITERS = {
    "csv": export_csv,
    "tsv": lambda p, l, c, m: export_csv(p, l, c, m, delimiter="\t"),
    "json": export_json,
    "xlsx": export_xlsx,
    "txt": export_txt,
    "html": export_html,
}


def write(fmt: str, path: str, leads: Sequence[Dict[str, Any]],
          columns: Sequence[str], meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    fmt = fmt.lower().strip()
    if fmt not in WRITERS:
        raise KeyError(f"unknown format '{fmt}' - pick one of {', '.join(WRITERS)}")
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    stats = WRITERS[fmt](path, leads, columns, meta)
    stats["format"] = fmt
    stats["path"] = path
    stats["bytes"] = os.path.getsize(path) if os.path.exists(path) else 0
    return stats


def suggest_path(fmt: str, query: str, outdir: str = "leads") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # transliterate accents so "São Paulo" becomes "sao-paulo", not "s-o-paulo"
    plain = unicodedata.normalize("NFKD", query or "")
    plain = plain.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:48] or "leads"
    return os.path.join(outdir, f"{slug}-{stamp}.{EXT.get(fmt, 'csv')}")
