"""Decide what the report says, once, for every output format.

The HTML and PDF renderers only lay these values out; any wording, key
badge, rule text or link target is worked out here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import ForeignKey, Index, Schema, Table, UniqueConstraint

UNNAMED = "(unnamed)"


@dataclass
class Ref:
    """A pointer to another table, linkable when that table is in the report."""
    text: str
    anchor: Optional[str] = None  # None: the target table isn't documented

    @property
    def documented(self) -> bool:
        return self.anchor is not None


@dataclass
class ColumnRow:
    position: int
    name: str
    data_type: str
    autoincrement: bool
    nullable: bool
    default: Optional[str]
    keys: list[str]            # any of "PK", "FK", "UQ"
    ref: Optional[Ref]
    comment: Optional[str]


@dataclass
class FkRow:
    name: str
    columns: list[str]
    target: Ref
    target_columns: list[str]
    rules: str                 # "on delete cascade / on update restrict", or ""


@dataclass
class RelRow:
    child: Ref
    child_columns: list[str]
    parent: Ref
    parent_columns: list[str]
    cardinality: str
    name: str


@dataclass
class Section:
    name: str
    anchor: str
    comment: Optional[str]
    columns: list[ColumnRow]
    has_comments: bool
    primary_key: list[str]
    primary_key_name: Optional[str]
    foreign_keys: list[FkRow]
    indexes: list[Index]
    uniques: list[UniqueConstraint]


@dataclass
class Report:
    title: str
    subtitle: str
    meta: list[tuple[str, str]]
    stats: list[tuple[int, str]]
    relationships: list[RelRow]
    sections: list[Section] = field(default_factory=list)


def _table_ref(schema: Schema, name: str, prefix: Optional[str] = None, text: Optional[str] = None) -> Ref:
    target = schema.table(name)
    return Ref(text or (f"{prefix}.{name}" if prefix else name), target.anchor if target else None)


def _rules(fk: ForeignKey) -> str:
    parts = [f"on delete {fk.on_delete.lower()}" if fk.on_delete else "",
             f"on update {fk.on_update.lower()}" if fk.on_update else ""]
    return " / ".join(p for p in parts if p)


def _section(t: Table, schema: Schema) -> Section:
    columns = []
    for i, c in enumerate(t.columns, 1):
        keys = [k for k, on in (("PK", c.primary_key), ("FK", c.foreign_key),
                                ("UQ", c.unique and not c.primary_key)) if on]
        ref = _table_ref(schema, c.references.partition(".")[0], text=c.references) if c.references else None
        columns.append(ColumnRow(i, c.name, c.data_type, c.autoincrement, c.nullable, c.default,
                                 keys, ref, c.comment))
    fks = [FkRow(fk.name or UNNAMED, fk.columns, _table_ref(schema, fk.ref_table, fk.ref_schema),
                 fk.ref_columns, _rules(fk)) for fk in t.foreign_keys]
    uniques = [UniqueConstraint(u.name or UNNAMED, u.columns) for u in t.unique_constraints]
    return Section(t.name, t.anchor, t.comment, columns, any(c.comment for c in t.columns),
                   t.primary_key, t.primary_key_name, fks, t.indexes, uniques)


def build_report(schema: Schema, title: Optional[str] = None) -> Report:
    n = len(schema.tables)
    engine = f"{schema.dialect} {schema.server_version or ''}".strip()
    meta = [("Database", schema.database), ("Engine", engine)]
    if schema.schema_name:
        meta.append(("Schema", schema.schema_name))
    meta.append(("Generated", f"{schema.generated_at:%Y-%m-%d %H:%M}"))

    stats = [(n, "tables"),
             (sum(len(t.columns) for t in schema.tables), "columns"),
             (len(schema.relationships), "relationships"),
             (sum(len(t.indexes) for t in schema.tables), "indexes")]

    rels = [RelRow(_table_ref(schema, r.child_table), r.child_columns,
                   _table_ref(schema, r.parent_table), r.parent_columns,
                   r.cardinality, r.name or "")
            for r in schema.relationships]

    return Report(
        title=title or f"{schema.database} schema",
        subtitle=f"Schema reference for {n} selected table{'s' if n != 1 else ''}",
        meta=meta,
        stats=stats,
        relationships=rels,
        sections=[_section(t, schema) for t in schema.tables],
    )
