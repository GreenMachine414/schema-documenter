"""PDF report: summary page, a full-size ERD page, then one section per table."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics import renderPDF
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from .canvas import erd_drawing
from .erd import Layout
from .erd import layout_erd
from .models import Schema
from .report import Ref, Section, build_report

INK = HexColor("#1d2b3a")
MUTED = HexColor("#5f6f82")
LINE = HexColor("#dde4ec")
HEAD = HexColor("#1f3a5f")
SOFT = HexColor("#f3f6f9")
KEY_COLORS = {"PK": "#0f766e", "FK": "#b45309", "UQ": "#6d28d9"}

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


def _ref(ref: Ref, columns=None) -> str:
    text = escape(ref.text) + (f" ({', '.join(escape(c) for c in columns)})" if columns is not None else "")
    return text if ref.documented else text + " (not documented)"


def _section(s: Section, width: float) -> list:
    out = [CondPageBreak(2.2 * inch)]
    head = [Paragraph(escape(s.name), S["h3"]), Paragraph(f"{len(s.columns)} columns", S["muted"])]
    if s.comment:
        head.append(Paragraph(escape(s.comment), S["body"]))

    rows = [[
        _p(c.position, "muted"),
        Paragraph(escape(c.name), S["monob" if "PK" in c.keys else "mono"]),
        Paragraph(escape(c.data_type) + (" <font color='#5f6f82'>auto</font>" if c.autoincrement else ""), S["mono"]),
        _p("Yes" if c.nullable else "No"),
        Paragraph(escape(c.default) if c.default is not None else "", S["mono"]),
        Paragraph(" ".join(f'<font color="{KEY_COLORS[k]}"><b>{k}</b></font>' for k in c.keys), S["cell"]),
        Paragraph(_ref(c.ref) if c.ref else "", S["mono"]),
    ] for c in s.columns]
    cols = _grid(["#", "Column", "Type", "Null", "Default", "Keys", "References"], rows,
                 [width * f for f in (0.04, 0.2, 0.18, 0.08, 0.16, 0.1, 0.24)])
    out.append(KeepTogether(head + [Paragraph("Columns", S["h4"]), cols]))

    out.append(Paragraph("Primary key", S["h4"]))
    if s.primary_key:
        name = f" &nbsp;<font color='#5f6f82'>({escape(s.primary_key_name)})</font>" if s.primary_key_name else ""
        out.append(Paragraph(", ".join(escape(c) for c in s.primary_key) + name, S["mono"]))
    else:
        out.append(Paragraph("No primary key.", S["muted"]))

    out.append(Paragraph("Foreign keys", S["h4"]))
    if s.foreign_keys:
        out.append(_grid(["Name", "Columns", "References", "Rules"],
                         [[Paragraph(escape(f.name), S["mono"]), _mono_list(f.columns),
                           Paragraph(_ref(f.target, f.target_columns), S["mono"]), _p(f.rules, "muted")]
                          for f in s.foreign_keys],
                         [width * f for f in (0.26, 0.2, 0.34, 0.2)]))
    else:
        out.append(Paragraph("No foreign keys.", S["muted"]))

    out.append(Paragraph("Indexes", S["h4"]))
    if s.indexes:
        out.append(_grid(["Name", "Columns", "Type"],
                         [[Paragraph(escape(ix.name), S["mono"]), _mono_list(ix.columns),
                           _p("Unique" if ix.unique else "Non-unique")] for ix in s.indexes],
                         [width * f for f in (0.42, 0.42, 0.16)]))
    else:
        out.append(Paragraph("No secondary indexes.", S["muted"]))

    if s.uniques:
        out.append(Paragraph("Unique constraints", S["h4"]))
        out.append(_grid(["Name", "Columns"],
                         [[Paragraph(escape(u.name), S["mono"]), _mono_list(u.columns)] for u in s.uniques],
                         [width * 0.5, width * 0.5]))
    out.append(Spacer(1, 18))
    return out


MIN_SCALE = 0.5  # below this the diagram continues onto more pages instead of shrinking


class DiagramSlice(Flowable):
    """One horizontal band [top, bottom) of the diagram, scaled to the page."""

    def __init__(self, drawing, top: float, bottom: float, scale: float):
        super().__init__()
        self.drawing, self.top, self.bottom, self.s = drawing, top, bottom, scale
        self.width, self.height = drawing.width * scale, (bottom - top) * scale

    def draw(self):
        c = self.canv
        clip = c.beginPath()
        clip.rect(0, 0, self.width, self.height)
        c.clipPath(clip, stroke=0, fill=0)
        c.scale(self.s, self.s)
        # drawing coordinates are y-up; show the band whose top-origin span is [top, bottom)
        renderPDF.draw(self.drawing, c, 0, -(self.drawing.height - self.bottom))


def _page_bands(lay: Layout, page_h: float) -> list[tuple[float, float]]:
    """Split the diagram at row gaps so each band fits `page_h`."""
    bands, start, last = [], 0.0, None
    for cut in lay.breaks + [lay.height]:
        if cut - start > page_h and last is not None and last > start:
            bands.append((start, last))
            start = last
        last = cut
    bands.append((start, lay.height))
    return bands


def _diagram_pages(schema: Schema, width: float, height: float) -> list:
    """Flowables for the diagram: one page when it's readable, otherwise several."""
    lay = layout_erd(schema, aspect=width / height)
    scale = min(1.0, width / lay.width, height / lay.height)
    if scale < MIN_SCALE:  # too big for one page: keep a readable size and continue downwards
        lay = layout_erd(schema, max_width=width / MIN_SCALE)
        scale = min(1.0, width / lay.width)
    drawing = erd_drawing(lay)
    bands = _page_bands(lay, height / scale)

    out = []
    for i, (top, bottom) in enumerate(bands):
        heading = "Entity relationship diagram"
        if len(bands) > 1:
            heading += f" (page {i + 1} of {len(bands)})"
        out += [PageBreak(), Paragraph(heading, S["h2"]), DiagramSlice(drawing, top, bottom, scale)]
    return out + [PageBreak()]


def render_pdf(schema: Schema, path: str | Path, title: Optional[str] = None) -> Path:
    path = Path(path)
    rep = build_report(schema, title)
    title = rep.title
    portrait = letter
    margin = 0.7 * inch
    width = portrait[0] - 2 * margin
    height = portrait[1] - 2 * margin

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(margin, 0.4 * inch, title)
        canvas.drawRightString(portrait[0] - margin, 0.4 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=portrait, title=title, author="Schema Documenter",
                          subject=f"Schema documentation for {schema.database}",
                          leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin)
    doc.addPageTemplates([PageTemplate("page", [Frame(margin, margin, width, height, id="p")], onPage=footer)])

    story: list = [Paragraph(escape(title), S["title"]), Spacer(1, 4),
                   Paragraph(escape(rep.subtitle), S["sub"]), Spacer(1, 14)]

    mt = Table([[_p(k, "muted"), _p(v, "body")] for k, v in rep.meta],
               colWidths=[1.1 * inch, width - 1.1 * inch], hAlign="LEFT")
    mt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story += [mt, Spacer(1, 16)]

    stats = Table([[Paragraph(str(v), S["stat"]) for v, _ in rep.stats],
                   [_p(label, "muted") for _, label in rep.stats]],
                  colWidths=[width / len(rep.stats)] * len(rep.stats), hAlign="LEFT")
    stats.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE),
                               ("TOPPADDING", (0, 0), (-1, 0), 8)]))
    story.append(stats)

    story.append(Paragraph("Tables", S["h2"]))
    summary = [[Paragraph(escape(s.name), S["mono"]), _p(len(s.columns)), _p(len(s.foreign_keys)),
                _p(len(s.indexes)), _p(s.comment or "", "muted")] for s in rep.sections]
    story.append(_grid(["Table", "Columns", "Foreign keys", "Indexes", "Comment"], summary,
                       [width * f for f in (0.32, 0.12, 0.14, 0.12, 0.30)]))

    story.append(Paragraph("Relationships", S["h2"]))
    if rep.relationships:
        rel_rows = [[Paragraph(_ref(r.child, r.child_columns), S["mono"]),
                     Paragraph(_ref(r.parent, r.parent_columns), S["mono"]),
                     _p(r.cardinality), Paragraph(escape(r.name), S["mono"])] for r in rep.relationships]
        story.append(_grid(["Table (foreign key)", "Refers to", "Cardinality", "Constraint"], rel_rows,
                           [width * f for f in (0.3, 0.3, 0.18, 0.22)]))
    else:
        story.append(Paragraph("None of the selected tables reference each other.", S["muted"]))

    story += _diagram_pages(schema, width - 12, height - 50) + [  # frame padding, heading room
              Paragraph("Table details", S["h2"])]
    for s in rep.sections:
        story += _section(s, width)

    doc.build(story)
    return path
