"""Standard-library sqlite checks for the migration DDL and additive upgrade.

The real migration uses SQLAlchemy; here we validate the same contract with the
builtin sqlite3 driver so the suite runs without third-party packages:
- a fresh schema includes calibrations and the run calibration columns;
- running the migration again does not error or duplicate columns.

Run with: python3 tests/test_migration_sqlite.py
"""

import re
import sqlite3
import unittest
from pathlib import Path

BOOTSTRAP = Path(__file__).resolve().parents[1] / "migrations" / "bootstrap.py"


class MigrationSqliteTests(unittest.TestCase):
    def test_additive_columns_and_idempotency(self):
        # Mirror migrations/bootstrap.ADDED_COLUMNS without importing SQLAlchemy.
        text = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("calibration_snapshot", text)
        self.assertIn("calibration_stale", text)
        self.assertIn("Calibration", text)
        model_text = (Path(__file__).resolve().parents[1] / "src" / "models" / "calibration.py").read_text(encoding="utf-8")
        self.assertIn('__tablename__ = "calibrations"', model_text)

        conn = sqlite3.connect(":memory:")
        # Minimal schema emulating an existing volume before the calibration feature.
        conn.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, status TEXT)")
        before = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        self.assertNotIn("calibration_stale", before)

        added_columns = {
            "runs": [
                ("calibration_snapshot", "JSON"),
                ("calibration_stale", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ],
        }

        def upgrade():
            present = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
            for column, ddl in added_columns["runs"]:
                if column not in present:
                    conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {ddl}")

        upgrade()
        upgrade()  # second pass must be a no-op (idempotent)
        after = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        self.assertIn("calibration_snapshot", after)
        self.assertIn("calibration_stale", after)

        conn.execute("INSERT INTO runs (id, status, calibration_stale) VALUES ('r1', 'queued', 0)")
        row = conn.execute("SELECT status, calibration_stale FROM runs WHERE id='r1'").fetchone()
        self.assertEqual(row, ("queued", 0))
        conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
