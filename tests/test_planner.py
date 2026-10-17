import copy
from datetime import datetime, timedelta, timezone
import random
import unittest
from campus_planner.models import InputError, PlanRequest
from campus_planner.planner import normalized_windows, schedule

BASE = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def stamp(minutes):
    return (BASE + timedelta(minutes=minutes)).isoformat()


def payload(tasks=None, windows=None):
    return {"now": stamp(0), "tasks": tasks if tasks is not None else [task("a", 60, 90)],
            "availability": [{"start": stamp(a), "end": stamp(b)} for a, b in (windows if windows is not None else [(0, 120)])]}


def task(identity, minutes, due, completed=0):
    return {"id": identity, "title": "Assignment " + identity, "estimate_minutes": minutes,
            "completed_minutes": completed, "due": stamp(due)}


class PlannerTests(unittest.TestCase):
    def test_exact_deadline_is_allowed(self):
        result = schedule(PlanRequest.parse(payload([task("a", 60, 60)])))
        self.assertTrue(result["feasible"])
        self.assertEqual(result["blocks"][0]["end"], stamp(60))

    def test_earliest_deadline_wins_regardless_of_input_order(self):
        result = schedule(PlanRequest.parse(payload([task("late", 60, 120), task("early", 60, 60)])))
        self.assertEqual([b["task_id"] for b in result["blocks"]], ["early", "late"])

    def test_splits_at_unavailable_gap(self):
        result = schedule(PlanRequest.parse(payload([task("a", 60, 120)], [(0, 30), (90, 120)])))
        self.assertEqual([b["minutes"] for b in result["blocks"]], [30, 30])
        self.assertTrue(result["feasible"])

    def test_overlaps_do_not_double_count_capacity(self):
        result = schedule(PlanRequest.parse(payload([task("a", 100, 120)], [(0, 60), (30, 90)])))
        self.assertEqual(result["scheduled_minutes"], 90)
        self.assertEqual(result["unscheduled_minutes"], 10)

    def test_never_schedules_in_the_past(self):
        result = schedule(PlanRequest.parse(payload([task("a", 90, 60)], [(-60, 60)])))
        self.assertEqual(result["blocks"][0]["start"], stamp(0))
        self.assertEqual(result["unscheduled_minutes"], 30)

    def test_overdue_task_has_specific_reason_and_does_not_take_future_time(self):
        result = schedule(PlanRequest.parse(payload([task("a", 30, -1), task("b", 60, 60)])))
        self.assertEqual(result["outcomes"][0]["reason"], "deadline_passed")
        self.assertEqual(result["outcomes"][1]["status"], "scheduled")

    def test_completed_work_is_not_scheduled_again(self):
        result = schedule(PlanRequest.parse(payload([task("a", 60, -1, 60), task("b", 60, 90, 30)])))
        self.assertTrue(result["feasible"])
        self.assertEqual(result["scheduled_minutes"], 30)
        self.assertEqual(result["outcomes"][0]["status"], "completed")

    def test_no_availability_and_no_tasks_are_distinct(self):
        self.assertFalse(schedule(PlanRequest.parse(payload(windows=[])))["feasible"])
        self.assertTrue(schedule(PlanRequest.parse(payload(tasks=[], windows=[])))["feasible"])

    def test_timezone_offsets_are_compared_as_instants(self):
        data = payload([task("a", 60, 120)], [])
        data["now"] = "2026-11-01T01:00:00-04:00"
        data["tasks"][0]["due"] = "2026-11-01T01:30:00-05:00"
        data["availability"] = [{"start": "2026-11-01T01:00:00-04:00", "end": "2026-11-01T01:00:00-05:00"}]
        self.assertEqual(schedule(PlanRequest.parse(data))["scheduled_minutes"], 60)

    def test_validation_rejects_ambiguous_and_malformed_inputs(self):
        invalid = []
        for field, value in [("estimate_minutes", True), ("estimate_minutes", -1), ("completed_minutes", 61), ("due", "2026-10-17T12:00"), ("due", "tomorrow"), ("due", "0001-01-01T00:00:00+01:00"), ("due", "2026-10-17T12:00:01Z")]:
            data = payload(); data["tasks"][0][field] = value; invalid.append(data)
        data = payload(); data["tasks"].append(copy.deepcopy(data["tasks"][0])); invalid.append(data)
        data = payload(); data["taskz"] = []; invalid.append(data)
        invalid.append(payload(windows=[(20, 10)]))
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(InputError):
                PlanRequest.parse(data)

    def test_seeded_random_schedules_satisfy_capacity_and_feasibility(self):
        # Independent feasibility check: with all work available now and splittable,
        # every deadline prefix must fit within the union of available time before it.
        rng = random.Random(42)
        for _ in range(150):
            tasks = [task(str(i), rng.randint(1, 90), rng.randint(1, 360)) for i in range(rng.randint(1, 12))]
            windows = [(start, start + rng.randint(1, 100)) for start in [rng.randint(-30, 300) for _ in range(8)]]
            request = PlanRequest.parse(payload(tasks, windows))
            result = schedule(request)
            availability = normalized_windows(request)
            expected_feasible = True
            for t in request.tasks:
                needed = sum(x.remaining for x in request.tasks if x.due <= t.due)
                capacity = sum(max(0, int((min(w.end, t.due) - w.start).total_seconds() // 60)) for w in availability)
                expected_feasible &= needed <= capacity
            self.assertEqual(result["feasible"], expected_feasible)
            self.assertEqual(result["scheduled_minutes"] + result["unscheduled_minutes"], sum(t.remaining for t in request.tasks))
            previous_end = request.now
            for block in result["blocks"]:
                start, end = datetime.fromisoformat(block["start"]), datetime.fromisoformat(block["end"])
                self.assertGreaterEqual(start, previous_end)
                self.assertTrue(any(w.start <= start < end <= w.end for w in availability))
                self.assertLessEqual(end, next(t.due for t in request.tasks if t.id == block["task_id"]))
                previous_end = end
