"""Create all tables directly (quick start / development). Production uses Alembic migrations."""

import app.models  # noqa: F401  (register models)
from app.db.base import Base
from app.db.session import engine


def main() -> None:
    Base.metadata.create_all(engine)
    print("Tables created")


if __name__ == "__main__":
    main()
