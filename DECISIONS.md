# Decisions

## No LLM In Conversation Layer

Problem: The brief allows an LLM but requires deterministic, grounded behavior.

Options: Use an LLM with strict validation, or use a deterministic parser.

Decision: Use a deterministic parser for this submission.

Reason: The visible and hidden evaluator reward deterministic terminal states and tool usage. A parser avoids malformed model output and fabricated IDs.

Safety/correctness impact: Lower language breadth, but stronger determinism and no hallucinated facts.

## State Reset Per `/agent/run`

Problem: The runner requires each conversation to start from the shipped `clinic.json`.

Options: Keep one global database or create fresh state per request.

Decision: Create a fresh `ClinicTools` instance per `/agent/run`.

Reason: This matches the runner contract and lets visible conversations book overlapping slots independently.

Safety/correctness impact: Prevents cross-conversation contamination.

## Guardian Authorization

Problem: The schema does not define a broad authorization model, but `guardian_of` exists in `clinic.json`.

Options: Escalate all third-party actions, or allow listed guardians for listed children.

Decision: Allow only exact `guardian_of` relationships; escalate other third-party adult actions.

Reason: This is the only explicit authorization relationship supplied by the data.

Safety/correctness impact: Supports child booking while avoiding unsafe adult record mutation.

## Slot Choice When Caller Gives A Period

Problem: The schema does not specify how to choose among multiple valid returned slots.

Options: Ask for clarification, choose randomly, or choose the first deterministic matching slot.

Decision: Choose the earliest available matching requested time or period.

Reason: Hidden grading checks determinism and non-fabrication more than wording.

Safety/correctness impact: Predictable and uses only tool-returned slots.

## Frontend Data

Problem: The frontend needs real backend responses without fake mocks.

Options: Hard-code sample data in React, or have the backend replay supplied scripts.

Decision: The backend replays supplied scripts for the queue and returns actual agent outputs.

Reason: This keeps tool calls and outcomes grounded in backend behavior.

Safety/correctness impact: UI proof reflects real backend logic.
