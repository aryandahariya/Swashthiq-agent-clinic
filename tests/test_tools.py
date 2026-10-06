from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.tools import ClinicTools, ToolError, ToolRecorder


def test_valid_slot_search():
    result = ClinicTools().search_slots("dr_rao", "2026-10-03")
    assert result["ok"] is True
    assert "09:00" in result["slots"]
    assert "09:15" not in result["slots"]


def test_invalid_slot_search_doctor():
    tools = ClinicTools()
    try:
        tools.search_slots("dr_missing", "2026-10-03")
    except ToolError as exc:
        assert exc.code == "unknown_doctor"
    else:
        raise AssertionError("expected ToolError")


def test_successful_booking_and_duplicate_booking():
    tools = ClinicTools()
    booked = tools.book_appointment("pt_0013", "dr_rao", "2026-10-03", "09:00")
    assert booked["appointment"]["id"] == "ap_0026"
    try:
        tools.book_appointment("pt_0014", "dr_rao", "2026-10-03", "09:00")
    except ToolError as exc:
        assert exc.code == "slot_unavailable"
    else:
        raise AssertionError("duplicate booking should fail")


def test_nonexistent_slot_rejected():
    tools = ClinicTools()
    try:
        tools.book_appointment("pt_0013", "dr_rao", "2026-10-04", "09:00")
    except ToolError as exc:
        assert exc.code == "slot_unavailable"
    else:
        raise AssertionError("Sunday booking should fail")


def test_concurrent_booking_allows_one_success():
    tools = ClinicTools()

    def attempt(index: int) -> bool:
        try:
            tools.book_appointment(f"pt_{index + 1:04d}", "dr_rao", "2026-10-03", "09:00")
            return True
        except ToolError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count(True) == 1


def test_patient_lookup_unique_and_ambiguous():
    tools = ClinicTools()
    assert tools.lookup_patient("Priya Nair", "9812200104")["status"] == "unique"
    ambiguous = tools.lookup_patient("Sharma")
    assert ambiguous["status"] == "ambiguous"
    assert len(ambiguous["candidates"]) == 3


def test_reschedule_cancel_and_invalid_mutations():
    tools = ClinicTools()
    moved = tools.reschedule_appointment("pt_0001", "dr_rao", "2026-10-01", "2026-10-03", "10:00")
    assert moved["appointment"]["date"] == "2026-10-03"
    cancelled = tools.cancel_appointment("pt_0001", "dr_rao", "2026-10-03")
    assert cancelled["appointment"]["status"] == "cancelled"
    try:
        tools.reschedule_appointment("pt_0001", "dr_rao", "2026-10-01", "2026-10-04", "10:00")
    except ToolError as exc:
        assert exc.code == "appointment_not_found"
    else:
        raise AssertionError("cancelled appointment should not reschedule")


def test_malformed_arguments_are_actionable():
    tools = ClinicTools()
    try:
        tools.book_appointment("pt_0013", "dr_rao", "2026/10/03", "09:00")
    except ToolError as exc:
        assert exc.code == "invalid_date"
    else:
        raise AssertionError("bad date should fail")


def test_date_format_is_strictly_iso():
    try:
        ClinicTools().search_slots("dr_rao", "2026-1-3")
    except ToolError as exc:
        assert exc.code == "invalid_date"
    else:
        raise AssertionError("non-padded dates should fail")


def test_same_slot_reschedule_is_not_reported_as_a_move():
    tools = ClinicTools()
    try:
        tools.reschedule_appointment("pt_0001", "dr_rao", "2026-10-01", "2026-10-01", "09:30")
    except ToolError as exc:
        assert exc.code == "unchanged_appointment"
    else:
        raise AssertionError("rescheduling to the current slot should fail")
    assert tools.data["appointments"][0]["date"] == "2026-10-01"
    assert tools.data["appointments"][0]["start"] == "09:30"


def test_malformed_and_unknown_tool_calls_return_recorded_errors():
    recorder = ToolRecorder(ClinicTools())
    malformed = recorder.call("lookup_patient", name=123)
    unknown = recorder.call("not_a_tool")
    assert malformed["ok"] is False
    assert malformed["error"]["code"] == "invalid_argument"
    assert unknown["ok"] is False
    assert unknown["error"]["code"] == "unknown_tool"
    assert [call.name for call in recorder.calls] == ["lookup_patient", "not_a_tool"]
