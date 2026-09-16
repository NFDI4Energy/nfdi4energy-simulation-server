"""Explicit, additive task-framework migration; safe to run more than once."""
import os
from sqlalchemy import inspect, text


def verify_framework(connection):
    columns = {column["name"] for column in inspect(connection).get_columns("tasks")}
    if "framework" not in columns:
        raise RuntimeError("Task framework migration required: run python -m "
                           "fastapi_app.persistence.migrate_framework before deploying the web application")
    invalid = connection.execute(text(
        "SELECT COUNT(*) FROM tasks WHERE framework IS NULL OR framework NOT IN ('dacedsx', 'mosaik')"
    )).scalar()
    if invalid:
        raise RuntimeError("Unexpected task framework values; inspect metadata before continuing")


def migrate(engine):
    from fastapi_app.persistence.models_db import Base
    with engine.begin() as connection:
        if not inspect(connection).has_table("tasks"):
            Base.metadata.create_all(bind=connection)
        elif "framework" not in {c["name"] for c in inspect(connection).get_columns("tasks")}:
            connection.execute(text(
                "ALTER TABLE tasks ADD COLUMN framework VARCHAR(16) NOT NULL DEFAULT 'dacedsx' "
                "CONSTRAINT task_framework_valid CHECK (framework IN ('dacedsx', 'mosaik'))"
            ))
        verify_framework(connection)


def main():
    from fastapi_app.persistence.database import create_database
    engine, _ = create_database(os.environ.get("DATABASE_URL", "sqlite:///./simserver_dev.db"))
    try:
        migrate(engine)
        print("Task framework migration verified.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
