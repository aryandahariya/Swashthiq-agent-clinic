from __future__ import annotations

import copy
import json
import re
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLINIC_PATH = ROOT / "swasthhiq" / "clinic.json"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ToolError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_result(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": self.message, "details": self.details}}


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]

    def public(self) -> dict[str, Any]:
        return {"name": self.name, "arguments": self.arguments}

    def full(self) -> dict[str, Any]:
        return {"name": self.name, "arguments": self.arguments, "result": self.result}


def load_clinic() -> dict[str, Any]:
    with CLINIC_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


class ClinicTools:
    """Authoritative, deterministic clinic operations. No LLM calls live here."""

    def __init__(self, data: dict[str, Any] | None = None):
        self.data = copy.deepcopy(data or load_clinic())
        self._lock = threading.RLock()

    @property
    def doctors(self) -> dict[str, dict[str, Any]]:
        return {doctor["id"]: doctor for doctor in self.data["doctors"]}

    @property
    def patients(self) -> dict[str, dict[str, Any]]:
        return {patient["id"]: patient for patient in self.data["patients"]}

    def _validate_doctor(self, doctor_id: str) -> dict[str, Any]:
        if not isinstance(doctor_id, str):
            raise ToolError("invalid_doctor", "Doctor id must be a string.", {"doctor_id": doctor_id})
        doctor = self.doctors.get(doctor_id)
        if not doctor:
            raise ToolError("unknown_doctor", f"No doctor exists with id {doctor_id}.", {"doctor_id": doctor_id})
        return doctor

    def _validate_patient(self, patient_id: str) -> dict[str, Any]:
        if not isinstance(patient_id, str):
            raise ToolError("invalid_patient", "Patient id must be a string.", {"patient_id": patient_id})
        patient = self.patients.get(patient_id)
        if not patient:
            raise ToolError("unknown_patient", f"No patient exists with id {patient_id}.", {"patient_id": patient_id})
        return patient

    @staticmethod
    def _validate_date(value: str) -> date:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ToolError("invalid_date", "Date must be YYYY-MM-DD.", {"date": value})
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError) as exc:
            raise ToolError("invalid_date", "Date must be YYYY-MM-DD.", {"date": value}) from exc

    @staticmethod
    def _validate_time(value: str) -> int:
        if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
            raise ToolError("invalid_time", "Time must be HH:MM.", {"time": value})
        hours, minutes = map(int, value.split(":"))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ToolError("invalid_time", "Time is outside a valid day.", {"time": value})
        return hours * 60 + minutes

    @staticmethod
    def _fmt(minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def _booked_starts(self, doctor_id: str, day: str, exclude_id: str | None = None) -> set[str]:
        return {
            appt["start"]
            for appt in self.data["appointments"]
            if appt["doctor_id"] == doctor_id
            and appt["date"] == day
            and appt["status"] == "booked"
            and appt["id"] != exclude_id
        }

    def _slots_for(self, doctor_id: str, day: str, exclude_id: str | None = None) -> list[str]:
        doctor = self._validate_doctor(doctor_id)
        parsed = self._validate_date(day)
        if day in self.data.get("holidays", []) or day in doctor.get("leave_dates", []):
            return []
        weekday = DAYS[parsed.weekday()]
        booked = self._booked_starts(doctor_id, day, exclude_id)
        slot_minutes = int(self.data["clinic"]["slot_minutes"])
        slots: set[str] = set()
        for window in doctor["windows"]:
            if window["day"] != weekday:
                continue
            start = self._validate_time(window["start"])
            end = self._validate_time(window["end"])
            cursor = start
            while cursor + slot_minutes <= end:
                label = self._fmt(cursor)
                if label not in booked:
                    slots.add(label)
                cursor += slot_minutes
        return sorted(slots)

    def search_slots(self, doctor_id: str, date: str) -> dict[str, Any]:
        with self._lock:
            slots = self._slots_for(doctor_id, date)
            return {"ok": True, "doctor_id": doctor_id, "date": date, "slots": slots}

    def book_appointment(self, patient_id: str, doctor_id: str, date: str, start: str) -> dict[str, Any]:
        with self._lock:
            self._validate_patient(patient_id)
            self._validate_doctor(doctor_id)
            self._validate_date(date)
            self._validate_time(start)
            if start not in self._slots_for(doctor_id, date):
                raise ToolError("slot_unavailable", "Requested slot is not available.", {
                    "doctor_id": doctor_id, "date": date, "start": start
                })
            next_number = max(int(appt["id"].split("_")[1]) for appt in self.data["appointments"]) + 1
            end = self._fmt(self._validate_time(start) + int(self.data["clinic"]["slot_minutes"]))
            appointment = {
                "id": f"ap_{next_number:04d}",
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "date": date,
                "start": start,
                "end": end,
                "status": "booked",
            }
            self.data["appointments"].append(appointment)
            return {"ok": True, "appointment": copy.deepcopy(appointment)}

    def _find_appointment(self, appointment_id: str | None = None, patient_id: str | None = None,
                          doctor_id: str | None = None, date: str | None = None) -> dict[str, Any]:
        matches = []
        for appt in self.data["appointments"]:
            if appt["status"] != "booked":
                continue
            if appointment_id and appt["id"] != appointment_id:
                continue
            if patient_id and appt["patient_id"] != patient_id:
                continue
            if doctor_id and appt["doctor_id"] != doctor_id:
                continue
            if date and appt["date"] != date:
                continue
            matches.append(appt)
        matches.sort(key=lambda item: (item["date"], item["start"], item["id"]))
        if not matches:
            raise ToolError("appointment_not_found", "No matching booked appointment exists.")
        if len(matches) > 1:
            raise ToolError("ambiguous_appointment", "More than one appointment matches.", {"appointments": matches})
        return matches[0]

    def reschedule_appointment(self, patient_id: str, doctor_id: str, current_date: str,
                               new_date: str, new_start: str) -> dict[str, Any]:
        with self._lock:
            appt = self._find_appointment(patient_id=patient_id, doctor_id=doctor_id, date=current_date)
            self._validate_date(new_date)
            self._validate_time(new_start)
            if new_date == appt["date"] and new_start == appt["start"]:
                raise ToolError("unchanged_appointment", "The appointment is already at that date and time.")
            if new_start not in self._slots_for(doctor_id, new_date, exclude_id=appt["id"]):
                raise ToolError("slot_unavailable", "Requested reschedule slot is not available.", {
                    "doctor_id": doctor_id, "date": new_date, "start": new_start
                })
            appt["date"] = new_date
            appt["start"] = new_start
            appt["end"] = self._fmt(self._validate_time(new_start) + int(self.data["clinic"]["slot_minutes"]))
            return {"ok": True, "appointment": copy.deepcopy(appt)}

    def cancel_appointment(self, patient_id: str, doctor_id: str | None = None, date: str | None = None) -> dict[str, Any]:
        with self._lock:
            appt = self._find_appointment(patient_id=patient_id, doctor_id=doctor_id, date=date)
            appt["status"] = "cancelled"
            return {"ok": True, "appointment": copy.deepcopy(appt)}

    def lookup_patient(self, name: str | None = None, phone: str | None = None,
                       dob: str | None = None) -> dict[str, Any]:
        with self._lock:
            for field, value in (("name", name), ("phone", phone), ("dob", dob)):
                if value is not None and not isinstance(value, str):
                    raise ToolError("invalid_argument", f"{field} must be a string.", {field: value})
            candidates = []
            wanted = norm(name or "")
            for patient in self.data["patients"]:
                if phone and patient["phone"] != phone:
                    continue
                if dob and patient["dob"] != dob:
                    continue
                if wanted:
                    pname = norm(patient["name"])
                    tokens = wanted.split()
                    if wanted not in pname and not all(token in pname for token in tokens):
                        continue
                candidates.append(copy.deepcopy(patient))
            candidates.sort(key=lambda item: item["id"])
            if not candidates:
                status = "not_found"
            elif len(candidates) == 1:
                status = "unique"
            else:
                status = "ambiguous"
            return {"ok": True, "status": status, "candidates": candidates}

    def escalate_to_human(self, reason: str, summary: str) -> dict[str, Any]:
        allowed = {"clinical_urgent", "medical_advice", "not_authorised", "ambiguous_patient", "out_of_scope"}
        if reason not in allowed:
            raise ToolError("invalid_escalation_reason", "Escalation reason is not allowed.", {"reason": reason})
        return {"ok": True, "reason": reason, "summary": summary}


class ToolRecorder:
    ALLOWED_TOOLS = {
        "search_slots", "book_appointment", "reschedule_appointment",
        "cancel_appointment", "lookup_patient", "escalate_to_human",
    }

    def __init__(self, tools: ClinicTools):
        self.tools = tools
        self.calls: list[ToolCall] = []

    def call(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        try:
            if tool_name not in self.ALLOWED_TOOLS:
                raise ToolError("unknown_tool", "Tool name is not allowed.", {"tool_name": tool_name})
            result = getattr(self.tools, tool_name)(**arguments)
        except ToolError as exc:
            result = exc.as_result()
        except TypeError as exc:
            result = ToolError("invalid_arguments", "Tool arguments are invalid.", {"message": str(exc)}).as_result()
        self.calls.append(ToolCall(name=tool_name, arguments=arguments, result=result))
        return result
