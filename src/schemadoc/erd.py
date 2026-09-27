"""Lay out an entity-relationship diagram without any external tools.

The layout is renderer-neutral: it produces boxes, rows and orthogonal edge
paths in a top-left-origin coordinate space. `draw_erd` then paints them onto
any `Canvas` (SVG for HTML, ReportLab for PDF), so both outputs match.

Layout approach, kept deliberately simple:
  1. Tables go on a grid. Related tables are placed close together by
     ordering them breadth-first, then improving positions with swaps that
     shorten the total distance between connected tables.
  2. Edges run only through the empty channels between grid rows and
     columns, so lines never cross over a table box.
  3. Crow's-foot notation marks cardinality at each end.
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional, Protocol

from reportlab.pdfbase.pdfmetrics import stringWidth

from .models import Relationship, Schema, Table

# ---- geometry constants (points / px; 1:1 in both renderers) -------------
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
TITLE_SIZE = 11
ROW_SIZE = 9
HEADER_H = 26
ROW_H = 18
PAD = 10
BADGE_W = 22
MIN_BOX_W = 170
MAX_BOX_W = 380
COL_GAP = 110
ROW_GAP = 70
MARGIN = 40
LANE_STEP = 7

THEME = {
    "paper": "#ffffff",
    "ink": "#1d2b3a",
    "muted": "#5f6f82",
    "box_border": "#9fb0c3",
    "header": "#1f3a5f",
    "header_text": "#ffffff",
    "row_alt": "#f3f6f9",
    "pk": "#0f766e",
    "fk": "#b45309",
    "edge": "#52667d",
}


def _w(text: str, size: float, bold: bool = False) -> float:
    return stringWidth(text, FONT_BOLD if bold else FONT, size)


def _truncate(text: str, size: float, max_w: float, bold: bool = False) -> str:
    if _w(text, size, bold) <= max_w:
        return text
    while text and _w(text + "…", size, bold) > max_w:
        text = text[:-1]
    return text + "…"


@dataclass
class Row:
    name: str
    type: str
    pk: bool
    fk: bool
    nullable: bool
    y: float = 0.0  # vertical centre, set during layout


@dataclass
class Box:
    table: Table
    w: float
    h: float
    rows: list[Row]
    x: float = 0.0
    y: float = 0.0
    col: int = 0
    row: int = 0

    def row_y(self, column: str) -> float:
        for r in self.rows:
            if r.name == column:
                return r.y
        return self.y + HEADER_H / 2


@dataclass
class Edge:
    rel: Relationship
    points: list[tuple[float, float]]
    start_dir: int   # +1 means the line leaves the child box heading right
    end_dir: int     # +1 means the line enters the parent box heading right


@dataclass
class Layout:
    width: float
    height: float
    boxes: list[Box] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


# ---------------------------------------------------------------- sizing
def _make_box(t: Table) -> Box:
    rows = [Row(c.name, c.data_type, c.primary_key, c.foreign_key, c.nullable) for c in t.columns]
    title_w = _w(t.name, TITLE_SIZE, True) + 2 * PAD
    name_w = max([_w(r.name, ROW_SIZE, r.pk) for r in rows] or [0])
    type_w = max([_w(r.type, ROW_SIZE) for r in rows] or [0])
    body_w = PAD + BADGE_W + name_w + 18 + type_w + PAD
    w = min(MAX_BOX_W, max(MIN_BOX_W, title_w, body_w))
    h = HEADER_H + max(1, len(rows)) * ROW_H + 4
    return Box(t, math.ceil(w), h, rows)


# ---------------------------------------------------------------- placement
def _order(names: list[str], adj: dict[str, set[str]]) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    by_degree = sorted(names, key=lambda n: (-len(adj[n]), n.lower()))
    for start in by_degree:
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        while queue:
            n = queue.popleft()
            order.append(n)
            for m in sorted(adj[n], key=lambda k: (-len(adj[k]), k.lower())):
                if m not in seen:
                    seen.add(m)
                    queue.append(m)
    return order


def _improve(cells: dict[str, tuple[int, int]], adj: dict[str, set[str]], slots: list[tuple[int, int]]):
    """Greedy swaps (including into empty slots) that reduce edge length."""
    def cost(name, pos):
        return sum(abs(pos[0] - cells[m][0]) + abs(pos[1] - cells[m][1]) for m in adj[name] if m != name)

    for _ in range(6):
        improved = False
        occupied = {pos: n for n, pos in cells.items()}
        names = list(cells)
        for a in names:
            for slot in slots:
                pa = cells[a]
                if slot == pa:
                    continue
                b = occupied.get(slot)
                before = cost(a, pa) + (cost(b, slot) if b else 0)
                cells[a] = slot
                if b:
                    cells[b] = pa
                after = cost(a, slot) + (cost(b, pa) if b else 0)
                if after < before:
                    occupied[slot] = a
                    if b:
                        occupied[pa] = b
                    else:
                        occupied.pop(pa, None)
                    improved = True
                else:
                    cells[a] = pa
                    if b:
                        cells[b] = slot
        if not improved:
            break


def layout_erd(schema: Schema) -> Layout:
    boxes = {t.name: _make_box(t) for t in schema.tables}
    if not boxes:
        return Layout(MARGIN * 2, MARGIN * 2)

    adj: dict[str, set[str]] = defaultdict(set)
    for name in boxes:
        adj[name]
    for r in schema.relationships:
        adj[r.child_table].add(r.parent_table)
        adj[r.parent_table].add(r.child_table)

    n = len(boxes)
    ncols = max(1, math.ceil(math.sqrt(n * 1.4)))
    nrows = math.ceil(n / ncols)
    slots = [(c, r) for r in range(nrows) for c in range(ncols)]
    order = _order(list(boxes), adj)
    cells = {name: slots[i] for i, name in enumerate(order)}
    _improve(cells, adj, slots)

    # compact away empty columns / rows left by the swaps
    used_cols = sorted({c for c, _ in cells.values()})
    used_rows = sorted({r for _, r in cells.values()})
    cmap = {c: i for i, c in enumerate(used_cols)}
    rmap = {r: i for i, r in enumerate(used_rows)}
    ncols, nrows = len(used_cols), len(used_rows)

    col_w = [0.0] * ncols
    row_h = [0.0] * nrows
    for name, (c, r) in cells.items():
        b = boxes[name]
        b.col, b.row = cmap[c], rmap[r]
        col_w[b.col] = max(col_w[b.col], b.w)
        row_h[b.row] = max(row_h[b.row], b.h)

    col_x = [MARGIN + sum(col_w[:i]) + COL_GAP * i for i in range(ncols)]
    row_y = [MARGIN + sum(row_h[:i]) + ROW_GAP * i for i in range(nrows)]
    for b in boxes.values():
        b.x, b.y = col_x[b.col], row_y[b.row]
        for i, row in enumerate(b.rows):
            row.y = b.y + HEADER_H + i * ROW_H + ROW_H / 2

    width = col_x[-1] + col_w[-1] + MARGIN
    height = row_y[-1] + row_h[-1] + MARGIN

    # channel centre lines: vchan[i] is left of column i, hchan[i] is above row i
    vchan = [col_x[0] - MARGIN / 2] + [
        (col_x[i - 1] + col_w[i - 1] + col_x[i]) / 2 for i in range(1, ncols)
    ] + [col_x[-1] + col_w[-1] + MARGIN / 2]
    hchan = [row_y[0] - MARGIN / 2] + [
        (row_y[i - 1] + row_h[i - 1] + row_y[i]) / 2 for i in range(1, nrows)
    ] + [row_y[-1] + row_h[-1] + MARGIN / 2]

    lanes: dict[tuple[str, int], int] = defaultdict(int)

    def lane(kind: str, idx: int, base: float, limit: float) -> float:
        k = lanes[(kind, idx)]
        lanes[(kind, idx)] += 1
        off = ((k + 1) // 2) * LANE_STEP * (1 if k % 2 else -1)
        return base + max(-limit, min(limit, off))

    v_limit = COL_GAP / 2 - 12
    h_limit = ROW_GAP / 2 - 10
    edges: list[Edge] = []
    for rel in schema.relationships:
        child, parent = boxes[rel.child_table], boxes[rel.parent_table]
        sy = child.row_y(rel.child_columns[0]) if rel.child_columns else child.y + HEADER_H / 2
        ey = parent.row_y(rel.parent_columns[0]) if rel.parent_columns else parent.y + HEADER_H / 2

        if parent.col > child.col:
            sdir, edir = 1, 1
            sv, ev = child.col + 1, parent.col
        elif parent.col < child.col:
            sdir, edir = -1, -1
            sv, ev = child.col, parent.col + 1
        else:  # same column (or self-reference): loop out the right side
            sdir, edir = 1, -1
            sv = ev = child.col + 1

        sx = child.x + child.w if sdir == 1 else child.x
        ex = parent.x if edir == 1 else parent.x + parent.w

        x1 = lane("v", sv, vchan[sv], v_limit)
        if sv == ev:
            if child is parent and abs(sy - ey) < 1:
                ey += ROW_H / 2  # degenerate self-loop on one column
            pts = [(sx, sy), (x1, sy), (x1, ey), (ex, ey)]
        else:
            x2 = lane("v", ev, vchan[ev], v_limit)
            candidates = {child.row, child.row + 1, parent.row, parent.row + 1}
            hi = min(candidates, key=lambda k: abs(hchan[k] - sy) + abs(hchan[k] - ey))
            yk = lane("h", hi, hchan[hi], h_limit)
            pts = [(sx, sy), (x1, sy), (x1, yk), (x2, yk), (x2, ey), (ex, ey)]
        edges.append(Edge(rel, pts, sdir, edir))

    return Layout(width, height, list(boxes.values()), edges)


# ---------------------------------------------------------------- drawing
class Canvas(Protocol):
    def rect(self, x, y, w, h, fill=None, stroke=None, radius=0, stroke_width=1): ...
    def line(self, x1, y1, x2, y2, stroke, width=1): ...
    def polyline(self, points, stroke, width=1): ...
    def circle(self, cx, cy, r, fill, stroke, width=1): ...
    def text(self, x, y, s, size, color, bold=False, anchor="start", link: Optional[str] = None): ...


def _markers(cv: Canvas, x: float, y: float, direction: int, many: bool, optional: bool, color: str):
    """Crow's-foot marker at a box edge. `direction` points *into* the box."""
    d = -direction  # points away from the box, back along the line
    if many:
        foot = 12
        cv.line(x + d * foot, y, x, y - 6, color, 1.2)
        cv.line(x + d * foot, y, x, y + 6, color, 1.2)
        cv.line(x + d * 16, y - 6, x + d * 16, y + 6, color, 1.2)
    else:
        cv.line(x + d * 8, y - 6, x + d * 8, y + 6, color, 1.2)
        if optional:
            cv.circle(x + d * 17, y, 4, THEME["paper"], color, 1.2)
        else:
            cv.line(x + d * 13, y - 6, x + d * 13, y + 6, color, 1.2)


def draw_erd(cv: Canvas, lay: Layout, link_tables: bool = False):
    t = THEME
    cv.rect(0, 0, lay.width, lay.height, fill=t["paper"])

    for e in lay.edges:
        cv.polyline(e.points, t["edge"], 1.2)
    for e in lay.edges:
        (sx, sy), (ex, ey) = e.points[0], e.points[-1]
        # child end: many (or one for 1:1); parent end: one / zero-or-one
        _markers(cv, sx, sy, -e.start_dir, many=not e.rel.one_to_one, optional=False, color=t["edge"])
        _markers(cv, ex, ey, e.end_dir, many=False, optional=e.rel.optional, color=t["edge"])

    for b in lay.boxes:
        cv.rect(b.x, b.y, b.w, b.h, fill=t["paper"], stroke=t["box_border"], radius=5)
        cv.rect(b.x, b.y, b.w, HEADER_H, fill=t["header"], radius=5)
        cv.rect(b.x, b.y + HEADER_H - 6, b.w, 6, fill=t["header"])  # square off header bottom
        title = _truncate(b.table.name, TITLE_SIZE, b.w - 2 * PAD, True)
        cv.text(b.x + PAD, b.y + HEADER_H / 2 + 4, title, TITLE_SIZE, t["header_text"], bold=True,
                link=("#" + b.table.anchor) if link_tables else None)

        if not b.rows:
            cv.text(b.x + PAD, b.y + HEADER_H + ROW_H / 2 + 3, "(no columns)", ROW_SIZE, t["muted"])
        for i, r in enumerate(b.rows):
            top = b.y + HEADER_H + i * ROW_H
            if i % 2:
                cv.rect(b.x + 1, top, b.w - 2, ROW_H, fill=t["row_alt"])
            base = r.y + 3.2
            if r.pk:
                cv.text(b.x + PAD, base, "PK", 7, t["pk"], bold=True)
            elif r.fk:
                cv.text(b.x + PAD, base, "FK", 7, t["fk"], bold=True)
            type_w = min(_w(r.type, ROW_SIZE), b.w * 0.45)
            name_space = b.w - PAD - BADGE_W - type_w - 14 - PAD
            name = _truncate(r.name, ROW_SIZE, name_space, r.pk)
            cv.text(b.x + PAD + BADGE_W, base, name, ROW_SIZE, t["ink"], bold=r.pk)
            rtype = _truncate(r.type, ROW_SIZE, b.w * 0.45)
            cv.text(b.x + b.w - PAD, base, rtype, ROW_SIZE, t["muted"], anchor="end")
        # redraw border on top of alternating row fills
        cv.rect(b.x, b.y, b.w, b.h, stroke=t["box_border"], radius=5)
