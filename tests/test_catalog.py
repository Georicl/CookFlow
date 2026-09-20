import copy
import json
import tempfile
import unittest
from pathlib import Path

from cookflow.catalog import connect, ingest, publish, validate, verify


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.con = connect(self.root / "catalog.sqlite")
        self.doc = json.loads((Path(__file__).resolve().parents[1] / "recipes/zh-CN/tomato-egg.json").read_text())

    def tearDown(self):
        self.con.close()
        self.temp.cleanup()

    def test_repeat_import_does_not_revert_current_version(self):
        self.assertEqual(ingest(self.con, self.doc)["version"], 1)
        newer = copy.deepcopy(self.doc)
        newer["title"] = "番茄炒蛋（修订）"
        self.assertEqual(ingest(self.con, newer)["version"], 2)
        self.assertFalse(ingest(self.con, self.doc)["changed"])
        self.assertEqual(self.con.execute("SELECT current_version FROM recipes").fetchone()[0], 2)

    def test_cycle_is_rejected_without_writing(self):
        self.doc["steps"][0]["depends_on"] = ["finish"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            ingest(self.con, self.doc)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM recipes").fetchone()[0], 0)

    def test_ready_requires_review_and_human_resource(self):
        self.doc["status"] = "ready"
        with self.assertRaisesRegex(ValueError, "review"):
            validate(self.doc)
        self.doc["review"] = {"by": "test reviewer", "at": "2026-09-20"}
        validate(self.doc)
        self.doc["steps"][0]["resources"].pop("person")
        with self.assertRaisesRegex(ValueError, "person"):
            validate(self.doc)

    def test_hold_must_follow_dependency_path(self):
        self.doc["resource_holds"][0]["from_step"] = "finish"
        self.doc["resource_holds"][0]["through_step"] = "egg"
        with self.assertRaisesRegex(ValueError, "depend"):
            validate(self.doc)

    def test_snapshot_is_independent_and_detects_corruption(self):
        ingest(self.con, self.doc)
        release = self.root / "release"
        publish(self.con, release)
        self.doc["title"] = "新版本"
        ingest(self.con, self.doc)
        self.assertEqual(verify(release)["versions"], 1)
        with (release / "catalog.sqlite").open("ab") as stream:
            stream.write(b"corruption")
        with self.assertRaisesRegex(ValueError, "checksum"):
            verify(release)


if __name__ == "__main__":
    unittest.main()
