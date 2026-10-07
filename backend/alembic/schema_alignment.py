"""Plan and apply the frozen 2026-10-07 schema without deleting legacy data."""
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from schema_20261007 import Base

REVISION = "20261007_schema_alignment"
METADATA = Base.metadata
ADD_DEFAULTS = {
    ("clubs", "opening_time"): "'08:00:00'",
    ("clubs", "closing_time"): "'22:00:00'",
    ("clubs", "view_count"): "0",
    ("clubs", "exposure_count"): "0",
    ("match_posts", "approval_required"): "0",
}


def _type_name(type_, dialect):
    # Reflection can append a column collation; preserve it without treating it
    # as a data type conversion. This revision does not change collations.
    name = str(type_.compile(dialect=dialect)).lower().replace(" ", "").split("characterset", 1)[0].split("collate", 1)[0]
    return "boolean" if name in ("bool", "boolean", "tinyint(1)") else name


def _count(connection, query):
    return connection.execute(sa.text(query)).scalar_one()


def plan_alignment(connection):
    """Preflight every data constraint before issuing the first MySQL DDL."""
    if connection.dialect.name != "mysql":
        raise RuntimeError("This alignment is tested for MySQL only")
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    actions = []
    for table in METADATA.sorted_tables:
        name = table.name
        if name not in tables:
            actions.append(("table", table))
            continue
        actual = {c["name"]: c for c in inspector.get_columns(name)}
        expected_pk = [c.name for c in table.primary_key.columns]
        if inspector.get_pk_constraint(name)["constrained_columns"] != expected_pk:
            raise RuntimeError(f"Unexpected primary key on {name}; manual review required")
        for column in table.columns:
            key = (name, column.name)
            if column.name not in actual:
                if not column.nullable and key not in ADD_DEFAULTS:
                    if _count(connection, f"SELECT COUNT(*) FROM `{name}`"):
                        raise RuntimeError(f"Cannot populate required column {name}.{column.name}")
                actions.append(("add", name, column))
                continue
            previous = actual[column.name]
            old_type = _type_name(previous["type"], connection.dialect)
            new_type = _type_name(column.type, connection.dialect)
            type_changed = old_type != new_type
            if type_changed:
                allowed = key == ("users", "ntrp_level") and old_type == "varchar(16)" and new_type == "decimal(2,1)"
                allowed |= key in (("clubs", "view_count"), ("clubs", "exposure_count")) and old_type == "integer" and new_type == "bigint"
                if not allowed:
                    raise RuntimeError(f"Unreviewed type conversion on {name}.{column.name}: {old_type} -> {new_type}")
                if key == ("users", "ntrp_level"):
                    invalid = _count(connection, "SELECT COUNT(*) FROM users WHERE ntrp_level IS NOT NULL AND ntrp_level NOT REGEXP '^[0-9]([.][0-9])?$'")
                    if invalid:
                        raise RuntimeError("NTRP values cannot be converted losslessly; resolve them before migrating")
            nullable_changed = previous["nullable"] != column.nullable
            if not column.nullable and nullable_changed:
                if _count(connection, f"SELECT COUNT(*) FROM `{name}` WHERE `{column.name}` IS NULL"):
                    raise RuntimeError(f"NULL values prevent NOT NULL on {name}.{column.name}")
            if type_changed or nullable_changed:
                actions.append(("alter", name, column, previous, type_changed))
        indexes = inspector.get_indexes(name)
        uniques = inspector.get_unique_constraints(name)
        for index in sorted(table.indexes, key=lambda x: x.name):
            columns = [c.name for c in index.columns]
            if any(i["column_names"] == columns and bool(i["unique"]) == index.unique for i in indexes):
                continue
            if any(i["name"] == index.name for i in indexes):
                raise RuntimeError(f"Index name collision on {name}.{index.name}")
            actions.append(("index", name, index.name, columns, index.unique))
        for constraint in table.constraints:
            if isinstance(constraint, sa.UniqueConstraint):
                columns = [c.name for c in constraint.columns]
                if any(u["column_names"] == columns for u in uniques) or any(i["column_names"] == columns and i["unique"] for i in indexes):
                    continue
                cname = constraint.name or "uq_" + name + "_" + "_".join(columns)
                if any(i["name"] == cname for i in indexes):
                    raise RuntimeError(f"Unique constraint name collision on {name}.{cname}")
                actions.append(("index", name, cname, columns, True))
            elif isinstance(constraint, sa.ForeignKeyConstraint):
                columns = [c.name for c in constraint.columns]
                target = constraint.elements[0].column.table.name
                target_columns = [e.column.name for e in constraint.elements]
                if any(f["constrained_columns"] == columns and f["referred_table"] == target and f["referred_columns"] == target_columns for f in inspector.get_foreign_keys(name)):
                    continue
                if all(c in actual for c in columns) and target in tables:
                    join = " AND ".join(f"s.`{c}` = t.`{d}`" for c, d in zip(columns, target_columns))
                    present = " AND ".join(f"s.`{c}` IS NOT NULL" for c in columns)
                    if _count(connection, f"SELECT COUNT(*) FROM `{name}` s LEFT JOIN `{target}` t ON {join} WHERE {present} AND t.`{target_columns[0]}` IS NULL"):
                        raise RuntimeError(f"Orphan references prevent foreign key on {name}")
                actions.append(("fk", name, "fk_" + name + "_" + "_".join(columns), columns, target, target_columns))
        # MySQL permits multiple NULLs in a unique index; only compare non-NULL keys.
        for action in actions:
            if action[0] == "index" and action[1] == name and action[4]:
                columns = action[3]
                if not all(c in actual for c in columns):
                    continue
                group = ", ".join(f"`{c}`" for c in columns)
                present = " AND ".join(f"`{c}` IS NOT NULL" for c in columns)
                if _count(connection, f"SELECT COUNT(*) FROM (SELECT {group} FROM `{name}` WHERE {present} GROUP BY {group} HAVING COUNT(*) > 1) duplicate_keys"):
                    raise RuntimeError(f"Duplicate values prevent unique index on {name}")
    return actions


def apply_alignment(connection):
    actions = plan_alignment(connection)
    operations = Operations(MigrationContext.configure(connection))
    for action in actions:
        kind = action[0]
        if kind == "table":
            table = action[1]
            table.dialect_options["mysql"]["charset"] = "utf8mb4"
            table.dialect_options["mysql"]["collate"] = "utf8mb4_unicode_ci"
            table.create(connection)
        elif kind == "add":
            _, name, column = action
            default = ADD_DEFAULTS.get((name, column.name))
            operations.add_column(name, sa.Column(column.name, column.type, nullable=column.nullable,
                server_default=sa.text(default) if default else None, comment=column.comment))
        elif kind == "alter":
            _, name, column, previous, type_changed = action
            kwargs = {"existing_type": previous["type"], "existing_nullable": previous["nullable"],
                "existing_server_default": sa.text(previous["default"]) if previous["default"] is not None else None,
                "existing_comment": previous.get("comment"),
                "nullable": column.nullable}
            if type_changed:
                kwargs["type_"] = column.type
            operations.alter_column(name, column.name, **kwargs)
        elif kind == "index":
            _, name, index_name, columns, unique = action
            operations.create_index(index_name, name, columns, unique=unique)
        elif kind == "fk":
            _, name, constraint_name, columns, target, target_columns = action
            operations.create_foreign_key(constraint_name, name, target, columns, target_columns)
    if plan_alignment(connection):
        raise RuntimeError("Schema still differs after alignment; revision was not stamped")
    return len(actions)
