"""Offline adapter for the data returned by Lehigh MCP's list_assignments.

Only explicit IDs, names and deadlines are retained. No token handling, grades,
submission bodies, calendar writes, or inferred completion status.
"""
from datetime import datetime, timezone
from .models import InputError, integer, text


def import_assignments(payload: dict, estimates: dict[str, int]) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("courses"), list):
        raise InputError("Moodle export must contain a courses list")
    if not isinstance(estimates, dict):
        raise InputError("estimates must map assignment IDs to effort in minutes")
    tasks, notices, seen = [], [], set()
    if payload.get("warnings"):
        notices.append("Moodle reported warnings; this export may be incomplete.")
    for course in payload["courses"]:
        if not isinstance(course, dict) or not isinstance(course.get("assignments"), list):
            raise InputError("Every course must contain an assignments list")
        for assignment in course["assignments"]:
            if not isinstance(assignment, dict):
                raise InputError("Each assignment must be an object")
            identity = str(integer(assignment.get("id"), "assignment.id", 1, 2**53 - 1))
            if identity in seen:
                raise InputError(f"Duplicate assignment ID: {identity}")
            seen.add(identity)
            due = integer(assignment.get("duedate", 0), "assignment.duedate", 0, 253402300799)
            if not due:
                notices.append(f"Assignment {identity} skipped: no due date.")
                continue
            if identity not in estimates:
                notices.append(f"Assignment {identity} skipped: provide an effort estimate.")
                continue
            estimate = integer(estimates[identity], f"estimates.{identity}", 1)
            # Round down to avoid scheduling beyond Moodle's exact deadline.
            deadline = datetime.fromtimestamp(due - due % 60, timezone.utc)
            tasks.append({"id": f"moodle:{identity}", "title": text(assignment.get("name"), "assignment.name"),
                          "due": deadline.isoformat(), "estimate_minutes": estimate})
    return {"tasks": tasks, "notices": notices}
