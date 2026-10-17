import argparse
import json
from pathlib import Path
import sqlite3
import sys
from .models import InputError, PlanRequest
from .moodle import import_assignments
from .planner import schedule
from .store import PlanStore


def read_json(path: str):
    return json.loads(Path(path).read_text())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Turn explicit deadlines and availability into an explainable study plan.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="Plan from a JSON request")
    plan.add_argument("input")
    plan.add_argument("--db", help="Also save an immutable plan in this SQLite database")
    plan.add_argument("--require-feasible", action="store_true", help="Exit 3 when any work cannot fit")
    history = sub.add_parser("history", help="List saved plan IDs")
    history.add_argument("--db", required=True)
    show = sub.add_parser("show", help="Retrieve a saved plan")
    show.add_argument("id")
    show.add_argument("--db", required=True)
    importer = sub.add_parser("import-moodle", help="Convert an exported list_assignments response; makes no network calls")
    importer.add_argument("input")
    importer.add_argument("--estimates", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            request = PlanRequest.parse(read_json(args.input))
            result = PlanStore(args.db).create(request) if args.db else schedule(request)
        elif args.command == "history":
            result = PlanStore(args.db).history()
        elif args.command == "show":
            result = PlanStore(args.db).get(args.id)
            if result is None:
                print("Plan not found", file=sys.stderr)
                return 4
        else:
            result = import_assignments(read_json(args.input), read_json(args.estimates))
    except (InputError, OSError, json.JSONDecodeError, sqlite3.Error) as error:
        # Avoid printing database/OS errors that may contain private filesystem paths.
        message = str(error) if isinstance(error, InputError) else "Could not read input or access the local database"
        print(f"Error: {message}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    if args.command == "plan" and args.require_feasible and not result["feasible"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
