"""Validate the same input contract for files, CLI calls, and the HTTP adapter."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class InputError(ValueError):
    """A user-correctable input error, safe to show at the application boundary."""


def instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise InputError(f"{field} must be an ISO 8601 timestamp with an offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InputError(f"{field} must be a valid ISO 8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InputError(f"{field} must include a timezone offset")
    if parsed.second or parsed.microsecond:
        raise InputError(f"{field} must be aligned to a whole minute")
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise InputError(f"{field} is outside the supported timestamp range") from None


def integer(value: Any, field: str, low: int = 0, high: int = 10080) -> int:
    if type(value) is not int or not low <= value <= high:
        raise InputError(f"{field} must be an integer between {low} and {high}")
    return value


def text(value: Any, field: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise InputError(f"{field} must be nonempty text of at most {maximum} characters")
    return value.strip()


def record(value: Any, field: str, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        raise InputError(f"{field} must be an object")
    if required - value.keys():
        raise InputError(f"{field} is missing: {', '.join(sorted(required - value.keys()))}")
    if value.keys() - required - (optional or set()):
        raise InputError(f"{field} contains unknown fields")
    return value


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    due: datetime
    estimate_minutes: int
    completed_minutes: int = 0

    @property
    def remaining(self) -> int:
        return self.estimate_minutes - self.completed_minutes


@dataclass(frozen=True, order=True)
class Window:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class PlanRequest:
    now: datetime
    tasks: tuple[Task, ...]
    availability: tuple[Window, ...]

    @classmethod
    def parse(cls, payload: Any) -> "PlanRequest":
        obj = record(payload, "request", {"now", "tasks", "availability"})
        now = instant(obj["now"], "now")
        if not isinstance(obj["tasks"], list) or len(obj["tasks"]) > 500:
            raise InputError("tasks must be a list of at most 500 tasks")
        if not isinstance(obj["availability"], list) or len(obj["availability"]) > 500:
            raise InputError("availability must be a list of at most 500 windows")
        tasks, ids = [], set()
        for index, raw in enumerate(obj["tasks"]):
            prefix = f"tasks[{index}]"
            row = record(raw, prefix, {"id", "title", "due", "estimate_minutes"}, {"completed_minutes"})
            identity = text(row["id"], prefix + ".id", 100)
            if identity in ids:
                raise InputError(f"duplicate task id: {identity}")
            ids.add(identity)
            estimate = integer(row["estimate_minutes"], prefix + ".estimate_minutes", 1)
            completed = integer(row.get("completed_minutes", 0), prefix + ".completed_minutes", 0, estimate)
            tasks.append(Task(identity, text(row["title"], prefix + ".title"),
                              instant(row["due"], prefix + ".due"), estimate, completed))
        windows = []
        for index, raw in enumerate(obj["availability"]):
            prefix = f"availability[{index}]"
            row = record(raw, prefix, {"start", "end"})
            start, end = instant(row["start"], prefix + ".start"), instant(row["end"], prefix + ".end")
            if start >= end:
                raise InputError(f"{prefix}.end must be after start")
            windows.append(Window(start, end))
        return cls(now, tuple(tasks), tuple(windows))

    def to_dict(self) -> dict:
        return {"now": self.now.isoformat(), "tasks": [
            {"id": t.id, "title": t.title, "due": t.due.isoformat(),
             "estimate_minutes": t.estimate_minutes, "completed_minutes": t.completed_minutes}
            for t in sorted(self.tasks, key=lambda t: t.id)],
            "availability": [{"start": w.start.isoformat(), "end": w.end.isoformat()}
                             for w in sorted(self.availability)]}
