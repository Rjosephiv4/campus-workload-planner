from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from campus_planner.api import create_app
from test_planner import payload


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(str(Path(self.temp.name) / "plans.db")))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def test_create_retrieve_and_retry(self):
        result = self.client.post("/v1/plans", json=payload())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.post("/v1/plans", json=payload()).json(), result.json())
        self.assertEqual(self.client.get("/v1/plans/" + result.json()["id"]).json(), result.json())
        self.assertEqual(len(self.client.get("/v1/plans").json()), 1)

    def test_validation_does_not_write_a_snapshot(self):
        self.assertEqual(self.client.post("/v1/plans", json={}).status_code, 422)
        self.assertEqual(self.client.get("/v1/plans").json(), [])
        self.assertEqual(self.client.get("/v1/plans?limit=101").status_code, 422)

    def test_missing_plan_is_404(self):
        self.assertEqual(self.client.get("/v1/plans/missing").status_code, 404)

    def test_shortfall_is_a_valid_explained_result(self):
        result = self.client.post("/v1/plans", json=payload(windows=[]))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["outcomes"][0]["reason"], "insufficient_time_before_deadline")
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
