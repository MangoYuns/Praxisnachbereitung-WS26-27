"""Teil A: Migration mit SQLite und Rückgabe-API mit isolierter DB-Attrappe.

Diese Tests ersetzen keinen Migrationstest gegen PostgreSQL.
Ausführen: python -m unittest discover -s tests -p test_tag4_a.py -v
Testabhängigkeit zusätzlich zur requirements.txt: httpx==0.28.1
"""

import importlib.util
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
import sqlalchemy as sa

from backend.app import main


class DamageNoteTests(unittest.TestCase):
    def test_upgrade_and_downgrade_preserve_existing_rows(self):
        path = Path(__file__).resolve().parents[1] / "alembic/versions/0001_assignment_damage_note.py"
        spec = importlib.util.spec_from_file_location("damage_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = sa.create_engine("sqlite://")
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE assignment (assignment_id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO assignment VALUES (1)")
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                column = next(c for c in sa.inspect(connection).get_columns("assignment") if c["name"] == "damage_note")
                self.assertTrue(column["nullable"])
                self.assertIsNone(connection.exec_driver_sql("SELECT damage_note FROM assignment").scalar())
                connection.execute(sa.text("UPDATE assignment SET damage_note = :note"), {"note": "Display zerkratzt"})
                self.assertEqual(connection.exec_driver_sql("SELECT damage_note FROM assignment").scalar(), "Display zerkratzt")
                migration.downgrade()
                self.assertNotIn("damage_note", [c["name"] for c in sa.inspect(connection).get_columns("assignment")])
                self.assertEqual(connection.exec_driver_sql("SELECT assignment_id FROM assignment").scalar(), 1)
                migration.upgrade()
                self.assertIsNone(connection.exec_driver_sql("SELECT damage_note FROM assignment").scalar())
        engine.dispose()

    def test_return_accepts_note_empty_note_and_old_clients(self):
        for payload, expected in [({"damage_note": "  Display zerkratzt  "}, "Display zerkratzt"),
                                  ({"damage_note": "   "}, None), ({"damage_note": None}, None), ({}, None), (None, None)]:
            with self.subTest(payload=payload):
                row = {"assignment_id": 1, "device_id": 1, "person_id": 1,
                       "issued_at": datetime(2026, 10, 24, tzinfo=timezone.utc),
                       "returned_at": None, "damage_note": None}
                updates = []

                class Connection:
                    def transaction(self):
                        return nullcontext()

                    def execute(self, query, params):
                        if query.lstrip().startswith("UPDATE"):
                            updates.append((query, params))
                            row.update(returned_at=datetime.now(timezone.utc), damage_note=params[1])
                        return self

                    def fetchone(self):
                        return row.copy()

                with patch.object(main, "get_conn", return_value=nullcontext(Connection())), \
                     patch.object(main, "publish_assignment_event") as publish:
                    with TestClient(main.app) as client:
                        response = client.post("/assignments/1/return", json=payload) if payload is not None else client.post("/assignments/1/return")
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["damage_note"], expected)
                    self.assertEqual(len(updates), 1)
                    self.assertIn("damage_note = %s", updates[0][0])
                    self.assertEqual(updates[0][1][1], expected)
                    publish.assert_called_once()

    def test_return_rejects_invalid_note_without_database_access(self):
        with patch.object(main, "get_conn") as connect, TestClient(main.app) as client:
            response = client.post("/assignments/1/return", json={"damage_note": {"invalid": True}})
        self.assertEqual(response.status_code, 422)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
