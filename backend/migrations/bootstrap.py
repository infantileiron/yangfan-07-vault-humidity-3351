"""Schema bootstrap for a fresh Compose volume, with lightweight additive upgrades."""
from sqlalchemy import inspect, text

from src.models.account import Account
from src.models.audit import Event
from src.models.calibration import Calibration
from src.models.dataset import Dataset
from src.models.review import Review
from src.models.run import Run

SCHEMA = (Account, Dataset, Run, Review, Event, Calibration)

# 既有部署的增量列：表名 -> (列名, 列 DDL 片段)。仅做加法，不改动历史数据。
ADDED_COLUMNS = {
    "runs": [
        ("calibration_snapshot", "JSON"),
        ("calibration_stale", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ],
}


def migrate(engine):
    tables = [model.__table__ for model in SCHEMA]
    Account.metadata.create_all(engine, tables=tables)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table_name, columns in ADDED_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns:
                if column_name not in present:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
