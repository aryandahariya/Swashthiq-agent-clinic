# SwasthiQ Clinic Front Desk Agent

Deterministic clinic front desk agent for the SwasthiQ assignment. The evaluator endpoint is `POST /agent/run`; every run reloads the supplied `swasthhiq/clinic.json` data so conversations are isolated.

## Architecture

- `backend/`: FastAPI REST API, rule-based conversation layer, deterministic tool layer.
- `frontend/`: React + Vite handoff queue and conversation detail UI backed by API responses.
- `adversarial/`: exactly 8 adversarial scripts in the assignment schema.
- `tests/`: backend, tool, concurrency, safety, and supplied-script regression tests.

The tool layer never calls an LLM. It owns all facts about doctors, patients, windows, holidays, appointments, and mutations. The conversation layer parses intent and calls tools; final booking, cancellation, reschedule, lookup, and escalation outcomes come from tool results.

## Six Tools

- `search_slots(doctor_id, date)`
- `book_appointment(patient_id, doctor_id, date, start)`
- `reschedule_appointment(patient_id, doctor_id, current_date, new_date, new_start)`
- `cancel_appointment(patient_id, doctor_id?, date?)`
- `lookup_patient(name?, phone?, dob?)`
- `escalate_to_human(reason, summary)`

All validation failures produce structured, actionable errors in the tool result or raised `ToolError` inside direct tests.

## Safety Model

Deterministic guards scan the whole transcript before ordinary scheduling. Urgent symptoms such as chest pain with breathlessness call `escalate_to_human` with `clinical_urgent` and no mutation tools. Medical advice requests are escalated with `medical_advice`. Prompt-injection and bulk-admin requests are refused without tools.

## Authorization And Identity

Patient lookup never guesses. Ambiguous patient matches escalate with `ambiguous_patient`. A caller acting for another adult is escalated with `not_authorised`. Listed guardians may act for children in `guardian_of`.

## API

Run evaluator endpoint:

```bash
POST /agent/run
```

Additional frontend endpoints:

```bash
GET /api/handoffs
GET /api/conversations/{conversation_id}
POST /api/handoffs/{conversation_id}/resolve
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Backend:

```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` if the backend is not at `http://localhost:8000`.

## Testing

```bash
pytest
cd swasthhiq
python runner.py --url http://localhost:8000/agent/run
python runner.py --repeat 3 --url http://localhost:8000/agent/run
python runner.py --dir ..\adversarial --url http://localhost:8000/agent/run
cd ..\frontend
npm run build
```

## Model And Measurements

No LLM is used in the submitted implementation. Model settings are therefore not applicable. `metrics.tokens` is a deterministic word-count estimate from caller turns; `metrics.latency_ms` is measured wall-clock processing time per request.

## Deployment

Run the FastAPI service with Uvicorn and serve the Vite build from any static host. Configure `VITE_API_URL` to point at the backend.

## Limitations

The conversation parser is deterministic and conservative. It covers the supplied assignment scripts and adversarial cases without fabricated facts, but hidden colloquial variants outside the implemented grammar may abandon or escalate instead of guessing.
