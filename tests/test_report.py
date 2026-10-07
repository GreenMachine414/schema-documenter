from schemadoc.models import Column, ForeignKey, Schema, Table
from schemadoc.report import build_report


def test_report_content(reader):
    rep = build_report(reader.read(["orders", "customers", "payments"]), "Shop")
    assert rep.title == "Shop"
    assert rep.subtitle == "Schema reference for 3 selected tables"
    assert dict((label, v) for v, label in rep.stats)["relationships"] == 2

    orders = next(s for s in rep.sections if s.name == "orders")
    cols = {c.name: c for c in orders.columns}
    assert cols["id"].keys == ["PK"]
    assert cols["customer_id"].keys == ["FK"]
    assert cols["customer_id"].ref.text == "customers.id" and cols["customer_id"].ref.documented
    # addresses wasn't selected, so the link is marked as not documented
    assert not cols["shipping_address_id"].ref.documented

    payments = next(s for s in rep.sections if s.name == "payments")
    assert {c.name: c.keys for c in payments.columns}["order_id"] == ["FK", "UQ"]


def test_fk_rules_and_external_targets():
    fk = ForeignKey("fk_addr_cust", ["customer_id"], "customers", ["id"], ref_schema="crm",
                    on_delete="CASCADE", on_update="RESTRICT")
    t = Table("addresses", columns=[Column("customer_id", "INTEGER", False, references="customers.id")],
              foreign_keys=[fk])
    rep = build_report(Schema("db", "postgresql", None, [t], []))
    row = rep.sections[0].foreign_keys[0]
    assert row.rules == "on delete cascade / on update restrict"
    assert row.target.text == "crm.customers" and not row.target.documented
    assert rep.title == "db schema" and rep.subtitle.endswith("1 selected table")
