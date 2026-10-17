# Lehigh MCP integration plan

The existing local MCP server exposes `list_assignments(course_ids)` and passes through Moodle's `mod_assign_get_assignments` response. Its `get_assignment_status(assignment_id)` uses assignment instance IDs. The planner's offline adapter uses that observed contract. Synthetic fixtures test the boundary; no student data is committed.

After the hackathon:

1. Add a separate MCP client adapter that requests only the explicitly selected course IDs. Keep the scheduling core network-independent.
2. Treat upstream warnings and failed course fetches as incomplete imports. Never interpret a partial response as assignment deletion.
3. Ask for estimates for new assignment IDs and persist those estimates separately from imported metadata. Moodle does not provide reliable effort estimates.
4. Read submission status explicitly before suggesting that work is incomplete. The current import does not infer it from deadlines or grades. Respect individual due-date extensions when those become available through the selected tool contract.
5. Keep source timestamps, course identity, and import provenance. Replanning should create a new snapshot; it must not overwrite old plans.
6. Add contract fixtures for empty courses, missing due dates, changed deadlines, repeated imports, partial failures, and completed submissions.

The first live integration remains read-only. Calendar event creation should be a separate explicit action with a preview and idempotency key; it is outside this version. Tokens belong to the MCP connection, never the planner database or repository. Personal exports go in an ignored `private/` directory.

## Interview exercise

Explain why earliest-deadline-first works for splittable tasks available now. Then show a counterexample when a task has a future release date or a prerequisite. Extend the model only after writing a failing test for that new constraint.
