"""Create all tables directly (quick start / development). Production uses Alembic migrations."""

from sqlalchemy import inspect, text

import app.models  # noqa: F401  (register models)
from app.db.base import Base
from app.db.session import engine

# Nullable columns added to existing tables after the first release (create_all only adds whole tables).
ADDED_COLUMNS = {
    "subscriptions": {
        "team_id": "INTEGER REFERENCES teams(id)",
        "usage_provider": "VARCHAR(20)",
        "seats_unnamed": "INTEGER DEFAULT 0",
        "function_id": "INTEGER REFERENCES functions(id)",
    },
    "teams": {
        "department_id": "INTEGER REFERENCES departments(id)",
        "function_id": "INTEGER REFERENCES functions(id)",
    },
    "employees": {
        "function_id": "INTEGER REFERENCES functions(id)",
    },
    "requests": {
        "function_id": "INTEGER REFERENCES functions(id)",
    },
}


def add_missing_columns() -> list[str]:
    added = []
    with engine.begin() as conn:
        for table, columns in ADDED_COLUMNS.items():
            existing = {c["name"] for c in inspect(conn).get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    added.append(f"{table}.{name}")
    return added


def main() -> None:
    Base.metadata.create_all(engine)
    added = add_missing_columns()
    print("Tables created" + (f"; columns added: {', '.join(added)}" if added else ""))


if __name__ == "__main__":
    main()
