from pypdf import PdfReader

from schemadoc.erd import layout_erd
from schemadoc.generate import generate

ALL = ["customers", "addresses", "categories", "products", "orders", "order_items", "payments", "audit_log"]


def test_html_report(reader, tmp_path):
    out = generate(reader, ALL, tmp_path / "doc", "html", title="Shop")
    html = out.read_text(encoding="utf-8")
    assert out.suffix == ".html"
    assert "<svg" in html and "Entity relationship diagram" in html
    for t in ALL:
        assert f"id='t-{t.replace('_', '-')}'" in html
    assert "ix_orders_customer_placed" in html


def test_pdf_report(reader, tmp_path):
    out = generate(reader, ALL, tmp_path / "doc.pdf", "pdf", title="Shop")
    pdf = PdfReader(str(out))
    text = "".join(p.extract_text() for p in pdf.pages)
    assert len(pdf.pages) >= 3
    assert "order_items" in text and "ux_products_sku" in text


def test_edges_avoid_boxes(reader):
    lay = layout_erd(reader.read(ALL))
    boxes = [(b.x, b.y, b.x + b.w, b.y + b.h) for b in lay.boxes]
    for e in lay.edges:
        pts = e.points
        # interior segments (not the stubs touching the boxes) must not pass through any box
        for (x1, y1), (x2, y2) in zip(pts[1:-1], pts[2:-1]):
            for bx1, by1, bx2, by2 in boxes:
                if x1 == x2:
                    hit = bx1 < x1 < bx2 and max(y1, y2) > by1 and min(y1, y2) < by2
                else:
                    hit = by1 < y1 < by2 and max(x1, x2) > bx1 and min(x1, x2) < bx2
                assert not hit, (e.rel, (x1, y1, x2, y2))
