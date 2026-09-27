"""PDF report: summary page, a full-size ERD page, then one section per table."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, KeepTogether, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from . import __version__
from .canvas import erd_drawing
from .erd import layout_erd
from .models import Schema
from .models import Table as DbTable

INK = HexColor("#1d2b3a")
MUTED = HexColor("#5f6f82")
LINE = HexColor("#dde4ec")
HEAD = HexColor("#1f3a5f")
SOFT = HexColor("#f3f6f9")
PK = "#0f766e"
FK = "#b45309"
UQ = "#6d28d9"

MAX_PAGE = 14000  # PDF viewers cap page size near 200 inches

S = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=INK),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=11, leading=15, textColor=MUTED),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=INK,
                         spaceBefore=16, spaceAfter=8, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName="Courier-Bold", fontSize=14, leading=18, textColor=HEAD,
                         spaceBefore=4, spaceAfter=2),
    "h4": ParagraphStyle("h4", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=MUTED,
                         spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK),
    "muted": ParagraphStyle("muted", fontName="Helvetica", fontSize=9, leading=12, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK,
                           alignment=TA_LEFT),
    "mono": ParagraphStyle("mono", fontName="Courier", fontSize=8.5, leading=11, textColor=INK),
    "monob": ParagraphStyle("monob", fontName="Courier-Bold", fontSize=8.5, leading=11, textColor=INK),
    "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=MUTED),
    "stat": ParagraphStyle("stat", fontName="Helvetica-Bold", fontSize=20, leading=23, textColor=HEAD),
}


def _p(text, style="cell"):
    return Paragraph(escape("" if text is None else str(text)).replace("\n", "<br/>"), S[style])


def _mono_list(cols):
    return Paragraph(", ".join(escape(c) for c in cols), S["mono"])


def _grid(header, rows, widths):
    data = [[Paragraph(escape(h), S["th"]) for h in header]] + rows
    tbl = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), SOFT),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    tbl.setStyle(TableStyle(style))
    return tbl


def _key_badges(c) -> Paragraph:
    parts = []
    if c.primary_key:
        parts.append(f'<font color="{PK}"><b>PK</b></font>')
    if c.foreign_key:
        parts.append(f'<font color="{FK}"><b>FK</b></font>')
    if c.unique and not c.primary_key:
        parts.append(f'<font color="{UQ}"><b>UQ</b></font>')
    return Paragraph(" ".join(parts), S["cell"])


def _table_flowables(t: DbTable, schema: Schema, width: float) -> list:
    out = [CondPageBreak(2.2 * inch)]
    head = [Paragraph(escape(t.name), S["h3"]),
            Paragraph(f"{len(t.columns)} columns", S["muted"])]
    if t.comment:
        head.append(Paragraph(escape(t.comment), S["body"]))

    rows = []
    for i, c in enumerate(t.columns, 1):
        ref = c.references or ""
        if ref and schema.table(ref.partition(".")[0]) is None:
            ref += " (not documented)"
        rows.append([
            _p(i, "muted"),
            Paragraph(escape(c.name), S["monob" if c.primary_key else "mono"]),
            Paragraph(escape(c.data_type) + (" <font color='#5f6f82'>auto</font>" if c.autoincrement else ""),
                      S["mono"]),
            _p("Yes" if c.nullable else "No"),
            Paragraph(escape(c.default) if c.default is not None else "", S["mono"]),
            _key_badges(c),
            Paragraph(escape(ref), S["mono"]),
        ])
    fr = [0.04, 0.2, 0.18, 0.08, 0.16, 0.1, 0.24]
    cols = _grid(["#", "Column", "Type", "Null", "Default", "Keys", "References"], rows,
                 [width * f for f in fr])
    out.append(KeepTogether(head + [Paragraph("Columns", S["h4"]), cols]))

    out.append(Paragraph("Primary key", S["h4"]))
    if t.primary_key:
        name = f" &nbsp;<font color='#5f6f82'>({escape(t.primary_key_name)})</font>" if t.primary_key_name else ""
        out.append(Paragraph(", ".join(escape(c) for c in t.primary_key) + name, S["mono"]))
    else:
        out.append(Paragraph("No primary key.", S["muted"]))

    out.append(Paragraph("Foreign keys", S["h4"]))
    if t.foreign_keys:
        fk_rows = []
        for fk in t.foreign_keys:
            target = f"{fk.ref_schema + '.' if fk.ref_schema else ''}{fk.ref_table}"
            if schema.table(fk.ref_table) is None:
                target += " (not documented)"
            rules = " / ".join(x for x in [
                f"on delete {fk.on_delete.lower()}" if fk.on_delete else "",
                f"on update {fk.on_update.lower()}" if fk.on_update else ""] if x)
            fk_rows.append([Paragraph(escape(fk.name or "(unnamed)"), S["mono"]), _mono_list(fk.columns),
                            Paragraph(f"{escape(target)} ({', '.join(escape(c) for c in fk.ref_columns)})",
                                      S["mono"]), _p(rules, "muted")])
        out.append(_grid(["Name", "Columns", "References", "Rules"], fk_rows,
                         [width * f for f in (0.26, 0.2, 0.34, 0.2)]))
    else:
        out.append(Paragraph("No foreign keys.", S["muted"]))

    out.append(Paragraph("Indexes", S["h4"]))
    if t.indexes:
        ix_rows = [[Paragraph(escape(ix.name), S["mono"]), _mono_list(ix.columns),
                    _p("Unique" if ix.unique else "Non-unique")] for ix in t.indexes]
        out.append(_grid(["Name", "Columns", "Type"], ix_rows, [width * f for f in (0.42, 0.42, 0.16)]))
    else:
        out.append(Paragraph("No secondary indexes.", S["muted"]))

    if t.unique_constraints:
        out.append(Paragraph("Unique constraints", S["h4"]))
        uq_rows = [[Paragraph(escape(u.name or "(unnamed)"), S["mono"]), _mono_list(u.columns)]
                   for u in t.unique_constraints]
        out.append(_grid(["Name", "Columns"], uq_rows, [width * 0.5, width * 0.5]))
    out.append(Spacer(1, 18))
    return out


def render_pdf(schema: Schema, path: str | Path, title: Optional[str] = None) -> Path:
    path = Path(path)
    title = title or f"{schema.database} schema"
    lay = layout_erd(schema)
    drawing = erd_drawing(lay)

    portrait = letter
    margin = 0.7 * inch
    width = portrait[0] - 2 * margin

    # ERD page is sized to the diagram so nothing gets squashed; viewers zoom.
    erd_margin = 0.5 * inch
    scale = min(1.0, MAX_PAGE / max(drawing.width, drawing.height))
    dw, dh = drawing.width * scale, drawing.height * scale
    drawing.scale(scale, scale)
    drawing.width, drawing.height = dw, dh
    title_h = 40
    land = landscape(letter)
    erd_size = (max(land[0], dw + 2 * erd_margin), max(land[1], dh + 2 * erd_margin + title_h))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        pw, _ = canvas._pagesize
        canvas.drawString(margin if pw == portrait[0] else erd_margin, 0.4 * inch, title)
        canvas.drawRightString(pw - (margin if pw == portrait[0] else erd_margin), 0.4 * inch,
                               f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=portrait, title=title, author="Schema Documenter",
                          subject=f"Schema documentation for {schema.database}",
                          leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin)
    doc.addPageTemplates([
        PageTemplate("portrait", [Frame(margin, margin, width, portrait[1] - 2 * margin, id="p")],
                     onPage=footer, pagesize=portrait),
        PageTemplate("erd", [Frame(erd_margin, erd_margin, erd_size[0] - 2 * erd_margin,
                                   erd_size[1] - 2 * erd_margin, id="e",
                                   leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
                     onPage=footer, pagesize=erd_size),
    ])

    story: list = [Paragraph(escape(title), S["title"]), Spacer(1, 4),
                   Paragraph(f"Schema reference for {len(schema.tables)} selected "
                             f"table{'s' if len(schema.tables) != 1 else ''}", S["sub"]), Spacer(1, 14)]

    meta = [["Database", schema.database], ["Engine", f"{schema.dialect} {schema.server_version or ''}".strip()]]
    if schema.schema_name:
        meta.append(["Schema", schema.schema_name])
    meta.append(["Generated", f"{schema.generated_at:%Y-%m-%d %H:%M}"])
    mt = Table([[_p(k, "muted"), _p(v, "body")] for k, v in meta], colWidths=[1.1 * inch, width - 1.1 * inch],
               hAlign="LEFT")
    mt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story += [mt, Spacer(1, 16)]

    n_cols = sum(len(t.columns) for t in schema.tables)
    n_idx = sum(len(t.indexes) for t in schema.tables)
    stats = Table([[Paragraph(str(v), S["stat"]) for v in (len(schema.tables), n_cols,
                                                          len(schema.relationships), n_idx)],
                   [_p(x, "muted") for x in ("tables", "columns", "relationships", "indexes")]],
                  colWidths=[width / 4] * 4, hAlign="LEFT")
    stats.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE),
                               ("TOPPADDING", (0, 0), (-1, 0), 8)]))
    story += [stats]

    story.append(Paragraph("Tables", S["h2"]))
    summary = [[Paragraph(escape(t.name), S["mono"]), _p(len(t.columns)), _p(len(t.foreign_keys)),
                _p(len(t.indexes)), _p(t.comment or "", "muted")] for t in schema.tables]
    story.append(_grid(["Table", "Columns", "Foreign keys", "Indexes", "Comment"], summary,
                       [width * f for f in (0.32, 0.12, 0.14, 0.12, 0.30)]))

    story.append(Paragraph("Relationships", S["h2"]))
    if schema.relationships:
        rel_rows = [[Paragraph(f"{escape(r.child_table)} ({', '.join(map(escape, r.child_columns))})", S["mono"]),
                     Paragraph(f"{escape(r.parent_table)} ({', '.join(map(escape, r.parent_columns))})", S["mono"]),
                     _p(r.cardinality), Paragraph(escape(r.name or ""), S["mono"])]
                    for r in schema.relationships]
        story.append(_grid(["Table (foreign key)", "Refers to", "Cardinality", "Constraint"], rel_rows,
                           [width * f for f in (0.3, 0.3, 0.18, 0.22)]))
    else:
        story.append(Paragraph("None of the selected tables reference each other.", S["muted"]))

    story += [NextPageTemplate("erd"), PageBreak(),
              Paragraph("Entity relationship diagram", S["h2"]), drawing,
              NextPageTemplate("portrait"), PageBreak(),
              Paragraph("Table details", S["h2"])]
    for t in schema.tables:
        story += _table_flowables(t, schema, width)

    doc.build(story)
    return path
