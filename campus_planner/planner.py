"""Earliest-deadline-first allocation for splittable work available immediately.

No priorities, dependencies, release dates, or guessed effort estimates. Explicit
capacity shortfalls are part of a successful result, not an exception.
"""
from datetime import timedelta
from .models import PlanRequest, Window

ALGORITHM = "edf-v1"


def normalized_windows(request: PlanRequest) -> list[Window]:
    merged: list[Window] = []
    for window in sorted(request.availability):
        start = max(window.start, request.now)
        if start >= window.end:
            continue
        if merged and start <= merged[-1].end:
            merged[-1] = Window(merged[-1].start, max(merged[-1].end, window.end))
        else:
            merged.append(Window(start, window.end))
    return merged


def schedule(request: PlanRequest) -> dict:
    windows = normalized_windows(request)
    cursors = [w.start for w in windows]
    blocks, outcomes = [], []
    for task in sorted(request.tasks, key=lambda t: (t.due, t.id)):
        remaining = task.remaining
        for i, window in enumerate(windows):
            if not remaining or cursors[i] >= task.due:
                break
            end = min(window.end, task.due)
            capacity = max(0, int((end - cursors[i]).total_seconds() // 60))
            minutes = min(remaining, capacity)
            if minutes:
                start = cursors[i]
                finish = start + timedelta(minutes=minutes)
                blocks.append({"task_id": task.id, "title": task.title,
                               "start": start.isoformat(), "end": finish.isoformat(), "minutes": minutes})
                cursors[i] = finish
                remaining -= minutes
        status = "completed" if task.remaining == 0 else "scheduled" if remaining == 0 else "at_risk"
        reason = None
        if remaining:
            reason = "deadline_passed" if task.due <= request.now else "insufficient_time_before_deadline"
        outcomes.append({"task_id": task.id, "title": task.title, "due": task.due.isoformat(),
                         "status": status, "scheduled_minutes": task.remaining - remaining,
                         "unscheduled_minutes": remaining, "reason": reason})
    blocks.sort(key=lambda b: (b["start"], b["task_id"]))
    return {"algorithm": ALGORITHM, "as_of": request.now.isoformat(),
            "feasible": all(o["unscheduled_minutes"] == 0 for o in outcomes),
            "scheduled_minutes": sum(b["minutes"] for b in blocks),
            "unscheduled_minutes": sum(o["unscheduled_minutes"] for o in outcomes),
            "blocks": blocks, "outcomes": outcomes}
