import pytest


def test_lists_tables(reader):
    assert reader.list_tables() == ["addresses", "audit_log", "categories", "customers",
                                    "order_items", "orders", "payments", "products"]


def test_columns_types_and_keys(reader):
    doc = reader.read(["customers", "orders", "order_items"])
    orders = doc.table("orders")
    cols = {c.name: c for c in orders.columns}
    assert orders.primary_key == ["id"]
    assert cols["id"].primary_key
    assert cols["customer_id"].references == "customers.id"
    assert not cols["customer_id"].nullable
    assert cols["status"].data_type.startswith("VARCHAR")
    assert any(ix.columns == ["customer_id", "placed_at"] for ix in orders.indexes)
    assert doc.table("order_items").primary_key == ["order_id", "product_id"]


def test_relationships_only_between_selected(reader):
    doc = reader.read(["orders", "customers"])
    rels = [(r.child_table, r.parent_table) for r in doc.relationships]
    assert rels == [("orders", "customers")]  # orders -> addresses is excluded


def test_cardinality(reader):
    doc = reader.read(["orders", "payments", "products", "categories", "addresses", "customers"])
    by = {(r.child_table, r.parent_table): r for r in doc.relationships}
    assert by[("payments", "orders")].one_to_one          # UNIQUE order_id
    assert not by[("orders", "customers")].one_to_one
    assert by[("products", "categories")].optional        # nullable FK
    assert ("categories", "categories") in by              # self reference


def test_unknown_table(reader):
    with pytest.raises(ValueError):
        reader.read(["nope"])
