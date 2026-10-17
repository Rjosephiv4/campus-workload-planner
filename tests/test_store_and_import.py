import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from campus_planner.models import InputError, PlanRequest
from campus_planner.moodle import import_assignments
from campus_planner.store import PlanStore
from test_planner import payload, task


class StoreTests(unittest.TestCase):
    def test_retries_and_reordered_inputs_do_not_duplicate_history(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plans.db"
            store = PlanStore(path)
            data = payload([task("b", 30, 120), task("a", 60, 90)])
            first = store.create(PlanRequest.parse(data))
            data["tasks"].reverse()
            second = store.create(PlanRequest.parse(data))
            self.assertEqual(first, second)
            self.assertEqual(len(store.history()), 1)
            self.assertEqual(PlanStore(path).get(first["id"]), first)
            self.assertIsNone(store.get("' OR 1=1 --"))

    def test_changed_estimate_creates_a_new_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            store = PlanStore(Path(temp) / "plans.db")
            data = payload()
            old = store.create(PlanRequest.parse(data))
            data["tasks"][0]["estimate_minutes"] = 120
            new = store.create(PlanRequest.parse(data))
            self.assertNotEqual(old["id"], new["id"])
            self.assertEqual(store.get(old["id"]), old)

    def test_cli_json_and_infeasible_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "input.json"
            source.write_text(json.dumps(payload(windows=[])))
            result = subprocess.run([sys.executable, "-m", "campus_planner.cli", "plan", str(source), "--require-feasible"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 3)
            self.assertFalse(json.loads(result.stdout)["feasible"])
            source.write_text("not json")
            result = subprocess.run([sys.executable, "-m", "campus_planner.cli", "plan", str(source)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)


class MoodleTests(unittest.TestCase):
    def test_import_uses_instance_id_and_drops_unneeded_private_data(self):
        source = {"courses": [{"id": 10, "assignments": [{"id": 7, "cmid": 99, "name": "SQL lab", "duedate": 1792245607, "intro": "private notes", "grade": 80}]}]}
        result = import_assignments(source, {"7": 60})
        self.assertEqual(result["tasks"][0]["id"], "moodle:7")
        self.assertNotIn("private notes", json.dumps(result))
        self.assertEqual(result["tasks"][0]["due"][-8:], "00+00:00")

    def test_missing_estimates_and_due_dates_are_explicit(self):
        source = {"courses": [{"assignments": [{"id": 1, "duedate": 0}, {"id": 2, "duedate": 1792245600}]}], "warnings": [{"message": "secret detail"}]}
        result = import_assignments(source, {})
        self.assertEqual(result["tasks"], [])
        self.assertEqual(len(result["notices"]), 3)
        self.assertNotIn("secret detail", json.dumps(result))

    def test_duplicate_assignment_cannot_be_counted_twice(self):
        source = {"courses": [{"assignments": [{"id": 1}, {"id": 1}]}]}
        with self.assertRaises(InputError):
            import_assignments(source, {})

    def test_malformed_export_fails(self):
        for source in ({}, {"courses": [None]}, {"courses": [{"assignments": [None]}]}):
            with self.assertRaises(InputError):
                import_assignments(source, {})
