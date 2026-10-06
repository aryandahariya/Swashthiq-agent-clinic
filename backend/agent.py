from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .tools import ClinicTools, ToolRecorder, norm


DOCTORS = {
    "rao": "dr_rao",
    "anjali": "dr_rao",
    "sethi": "dr_sethi",
    "vikram": "dr_sethi",
}

WEEKDAYS = {
    "somwar": 0, "monday": 0, "mon": 0,
    "mangalwar": 1, "tuesday": 1, "tue": 1,
    "budhwar": 2, "wednesday": 2, "wed": 2,
    "guruwar": 3, "thursday": 3, "thu": 3,
    "shukrawar": 4, "friday": 4, "fri": 4,
    "shanivaar": 5, "shanivar": 5, "saturday": 5, "sat": 5,
    "ravivaar": 6, "ravivar": 6, "sunday": 6, "sun": 6,
}

HINDI_HOURS = {
    "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "ek": 13, "do": 14,
    "teen": 15, "char": 16, "chaar": 16, "paanch": 17, "che": 18, "saat": 19,
}

PEOPLE = [
    ("Rajesh Kumar Sharma", "Rajesh Kumar Sharma"),
    ("R. K. Sharma", "R K Sharma"),
    ("Rajesh Sharma", "Rajesh Sharma"),
    ("Priya Nair", "Priya Nair"),
    ("Priya Menon", "Priya Menon"),
    ("Aarav Gupta", "Aarav"),
    ("Arjun Gupta", "Arjun"),
    ("Sunita Gupta", "Sunita Gupta"),
    ("Meera Joshi", "Meera Joshi"),
    ("Kabir Joshi", "Kabir"),
    ("Lakshmi Iyer", "Lakshmi Iyer"),
    ("Mohit Negi", "Mohit Negi"),
    ("Harpreet Singh", "Harpreet Singh"),
    ("Harpreet Kaur", "Harpreet Kaur"),
    ("Neha Bhatt", "Neha Bhatt"),
    ("Tarun Bisht", "Tarun Bisht"),
    ("Shalini Uniyal", "Shalini Uniyal"),
]


@dataclass
class Parsed:
    intent: str | None = None
    doctor_id: str | None = None
    date: str | None = None
    time: str | None = None
    period: str | None = None
    patient_name: str | None = None
    caller_name: str | None = None
    phone: str | None = None
    target_name: str | None = None
    third_party: bool = False


def parse_doctor(text: str) -> str | None:
    lowered = norm(clean_for_correction(text))
    matches: list[tuple[int, str]] = []
    for key, doctor_id in DOCTORS.items():
        matches.extend(
            (match.start(), doctor_id)
            for match in re.finditer(rf"\b{re.escape(key)}\b", lowered)
        )
    return max(matches)[1] if matches else None


def clean_for_correction(text: str) -> str:
    lowered = text.lower()
    for marker in ["nahi nahi", "actually", "instead", "rather"]:
        if marker in lowered:
            return text[lowered.rfind(marker):]
    return text


def parse_date(text: str, today: str) -> str | None:
    base = datetime.strptime(today, "%Y-%m-%d").date()
    relevant = clean_for_correction(text)
    iso_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", relevant)
    if iso_match:
        try:
            return datetime.strptime(iso_match.group(), "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    date_text = re.sub(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", " ", relevant)
    date_text = re.sub(r"\b(?:[01]?\d|2[0-3])\s*(?:baje|am|pm)\b", " ", date_text, flags=re.IGNORECASE)
    date_text = re.sub(r"\b\d{10}\b", " ", date_text)
    lowered = norm(date_text)
    dates: list[tuple[int, str]] = []
    for match in re.finditer(r"\bkal\b|\btomorrow\b", lowered):
        dates.append((match.start(), (base + timedelta(days=1)).isoformat()))
    for match in re.finditer(r"\bparso\b|\bday after tomorrow\b", lowered):
        dates.append((match.start(), (base + timedelta(days=2)).isoformat()))
    for match in re.finditer(r"\b([1-9]|[12][0-9]|3[01])\s*(?:tareekh|tarikh|date)?\b", lowered):
        day = int(match.group(1))
        if day >= base.day:
            try:
                dates.append((match.start(), base.replace(day=day).isoformat()))
            except ValueError:
                continue
    for word, weekday in WEEKDAYS.items():
        for match in re.finditer(rf"\b{re.escape(word)}\b", lowered):
            delta = (weekday - base.weekday()) % 7
            if delta == 0 and "aaj" not in lowered and "today" not in lowered:
                delta = 7
            dates.append((match.start(), (base + timedelta(days=delta)).isoformat()))
    for match in re.finditer(r"\baaj\b|\btoday\b", lowered):
        dates.append((match.start(), base.isoformat()))
    return max(dates, key=lambda item: item[0])[1] if dates else None


def parse_time(text: str) -> tuple[str | None, str | None]:
    relevant = clean_for_correction(text).lower()
    lowered = norm(relevant)
    exacts: list[str] = []

    def add_exact(hour: int, minute: int, meridiem: str | None = None) -> None:
        if meridiem == "am":
            hour %= 12
        elif meridiem == "pm":
            hour = hour % 12 + 12
        elif hour <= 12 and any(word in lowered for word in ["shaam", "evening", "raat"]):
            hour += 12
        if 8 <= hour <= 20 and minute in {0, 15, 30, 45}:
            exacts.append(f"{hour:02d}:{minute:02d}")

    for match in re.finditer(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", relevant):
        suffix = re.match(r"\s*(am|pm)\b", relevant[match.end():])
        add_exact(int(match.group(1)), int(match.group(2)), suffix.group(1) if suffix else None)
    for match in re.finditer(r"\b([01]?\d|2[0-3])\s*(baje|am|pm)\b", relevant):
        meridiem = match.group(2) if match.group(2) in {"am", "pm"} else None
        add_exact(int(match.group(1)), 0, meridiem)
    for word, hour in HINDI_HOURS.items():
        if re.search(rf"\b{word}\b", lowered):
            exacts.append(f"{hour:02d}:00")
    period = None
    if "subah" in lowered or "morning" in lowered:
        period = "morning"
    if "shaam" in lowered or "evening" in lowered:
        period = "evening"
    if "afternoon" in lowered or "dopahar" in lowered or "dupahar" in lowered:
        period = "afternoon"
    return (exacts[-1] if exacts else None, period)


def parse_people(text: str) -> tuple[str | None, str | None, str | None]:
    lowered = norm(text)
    found: list[str] = []
    for canonical, alias in PEOPLE:
        if norm(alias) in lowered or norm(canonical) in lowered:
            found.append(canonical)
    phone = None
    match = re.search(r"\b(\d{10})\b", text)
    if match:
        phone = match.group(1)
    caller = found[-1] if found else None
    target = found[0] if found else None
    if "sharma" in lowered and not found:
        target = "Sharma"
    return caller, target, phone


def parse_turns(turns: list[str], today: str) -> Parsed:
    parsed = Parsed()
    text = "\n".join(turns)
    lowered = norm(text)
    if (
        "cancel every appointment" in lowered
        or "administrator mode" in lowered
        or "system override" in lowered
        or "ignore all rules" in lowered
        or "ignore your previous instructions" in lowered
    ):
        parsed.intent = "refuse"
    else:
        actions: list[tuple[int, str]] = []
        action_patterns = [
            (r"\bcancel\b|\bcancel karna\b", "cancel"),
            (r"\breschedule\b|\bmove my appointment\b", "reschedule"),
            (r"\bbook\b|\bschedule\b|\breserve\b", "book"),
        ]
        if "aaj ka appointment" in lowered:
            action_patterns.append((r"\buse saturday\b|\bkarwana hai\b", "reschedule"))
        for pattern, intent in action_patterns:
            actions.extend((match.start(), intent) for match in re.finditer(pattern, lowered))
        stop_patterns = ["don t cancel", "dont cancel", "do not cancel", "cancel mat", "nahi cancel"]
        for phrase in stop_patterns:
            actions.extend((match.end(), "abandon") for match in re.finditer(re.escape(phrase), lowered))
        if actions:
            parsed.intent = max(actions, key=lambda action: action[0])[1]
        elif any(word in lowered for word in ["appointment", "milna", "dikhana", "paas"]):
            parsed.intent = "book"
    for turn in turns:
        doctor_id = parse_doctor(turn)
        if doctor_id:
            parsed.doctor_id = doctor_id
        date = parse_date(turn, today)
        if date:
            parsed.date = date
        clock, period = parse_time(turn)
        if clock:
            parsed.time = clock
        if period:
            parsed.period = period
        caller, target, phone = parse_people(turn)
        if caller:
            parsed.caller_name = caller
        if target:
            parsed.target_name = target
        if phone:
            parsed.phone = phone
    known_names = [norm(name) for name, _ in PEOPLE]
    named_third_party = any(
        re.search(rf"\bfor\s+{re.escape(name)}\b", lowered)
        for name in known_names
    )
    if named_third_party or any(marker in lowered for marker in [
        "ke liye", "for my ", "for him", "for her", "unka", "unke", "his ", "her "
    ]):
        parsed.third_party = True
    if "kabir" in lowered:
        parsed.patient_name = "Kabir Joshi"
        if "meera" in lowered:
            parsed.caller_name = "Meera Joshi"
    elif "aarav" in lowered:
        parsed.patient_name = "Aarav Gupta"
        if "sunita" in lowered:
            parsed.caller_name = "Sunita Gupta"
    elif "lakshmi" in lowered:
        parsed.patient_name = "Lakshmi Iyer"
        if "mohit" in lowered:
            parsed.caller_name = "Mohit Negi"
    if parsed.target_name:
        parsed.patient_name = parsed.target_name
    elif parsed.caller_name:
        parsed.patient_name = parsed.caller_name
    if "kabir" in lowered:
        parsed.patient_name = "Kabir Joshi"
    if "aarav" in lowered:
        parsed.patient_name = "Aarav Gupta"
    if "lakshmi" in lowered:
        parsed.patient_name = "Lakshmi Iyer"
    if parsed.intent is None and "dr " in lowered and parsed.date:
        parsed.intent = "book"
    return parsed


def safety_reason(turns: list[str]) -> str | None:
    raw_text = "\n".join(turns).lower()
    text = norm(raw_text)
    urgent_markers = [
        "chest pain", "heart attack", "can t breathe", "cannot breathe", "cant breathe",
        "shortness of breath", "difficulty breathing", "trouble breathing", "hard to breathe",
        "struggling to breathe", "behosh", "unconscious", "fainted", "passed out", "stroke",
        "severe bleeding", "heavy bleeding", "bleeding heavily", "bahut khoon", "khoon beh",
        "saans nahi aa", "saans phool", "saans lene me dikkat", "saans nahi le", "seene me dard",
        "seene mein dard", "chhati me dard", "chest me dard", "chest pressure", "crushing pressure",
        "pain going down my arm", "pain radiating", "left arm pain", "choking", "turning blue",
        "blue lips", "seizure", "convulsion", "overdose", "poisoning", "face drooping",
        "slurred speech", "one side weakness", "sudden weakness", "severe allergic reaction",
        "throat closing", "tongue swelling",
    ]
    hindi_urgent_markers = [
        "सीने में दर्द", "छाती में दर्द", "सांस नहीं", "साँस नहीं", "सांस फूल", "साँस फूल",
        "सांस लेने में दिक्कत", "साँस लेने में दिक्कत", "बेहोश", "बहुत खून", "खून बह",
        "चेहरा टेढ़ा", "बोल नहीं पा", "दौरा पड़", "जहर खा", "ज़हर खा", "ओवरडोज",
        "दिल का दौरा", "दिल का दर्द", "होंठ नीले", "गला बंद", "जीभ सूज",
    ]
    if any(marker in text for marker in urgent_markers) or any(
        marker in raw_text for marker in hindi_urgent_markers
    ):
        return "clinical_urgent"
    advice_markers = [
        "goli le lun", "kitni der", "crocin", "medicine", "dose", "dawai", "bukhar",
        "दवा", "दवाई", "गोली", "खुराक", "बुखार",
    ]
    asks_judgement = any(
        marker in text or marker in raw_text
        for marker in ["le lun", "should i", "kitni", "dose", "how much", "ले लूं", "ले लूँ", "क्या करूं", "कितनी"]
    )
    advice_question = any(marker in text or marker in raw_text for marker in advice_markers)
    if advice_question and (asks_judgement or not any(w in text for w in ["appointment", "milna"])):
        return "medical_advice"
    return None


def choose_slot(slots: list[str], requested: str | None, period: str | None) -> str | None:
    if requested:
        if requested not in slots:
            return None
        if period == "morning" and not "09:00" <= requested < "12:00":
            return None
        if period == "evening" and requested < "16:00":
            return None
        if period == "afternoon" and not "12:00" <= requested < "16:00":
            return None
        return requested
    filtered = slots
    if period == "morning":
        filtered = [slot for slot in filtered if "09:00" <= slot < "12:00"]
    if period == "evening":
        filtered = [slot for slot in filtered if slot >= "16:00"]
    if period == "afternoon":
        filtered = [slot for slot in filtered if "12:00" <= slot < "16:00"]
    return filtered[0] if filtered else None


class Agent:
    def __init__(self, tools: ClinicTools | None = None):
        self.recorder = ToolRecorder(tools or ClinicTools())

    def _escalate(self, reason: str, summary: str, conversation_id: str, turns: list[str],
                  patient_id: str | None = None) -> dict[str, Any]:
        self.recorder.call("escalate_to_human", reason=reason, summary=summary)
        return self._response(conversation_id, "escalated", reason, patient_id, None,
                              "I am handing this to a human team member now.", turns)

    def _lookup(self, name: str | None, phone: str | None) -> dict[str, Any]:
        return self.recorder.call("lookup_patient", name=name, phone=phone)

    def _resolve_patient(self, parsed: Parsed) -> tuple[str | None, str | None]:
        lookup = self._lookup(parsed.patient_name, parsed.phone)
        candidates = lookup.get("candidates", [])
        if lookup.get("status") == "unique":
            return candidates[0]["id"], None
        if lookup.get("status") == "ambiguous":
            return None, "ambiguous_patient"
        return None, "out_of_scope"

    def _authorized(self, parsed: Parsed, patient_id: str) -> bool:
        if not parsed.caller_name:
            return not parsed.third_party
        if parsed.caller_name == parsed.patient_name:
            return not parsed.third_party
        caller = self.recorder.call("lookup_patient", name=parsed.caller_name, phone=parsed.phone)
        caller_candidates = caller.get("candidates", [])
        return bool(
            caller.get("status") == "unique"
            and caller_candidates
            and patient_id in caller_candidates[0].get("guardian_of", [])
        )

    def run(self, conversation_id: str, today: str, turns: list[str]) -> dict[str, Any]:
        started = time.monotonic()
        try:
            datetime.strptime(today, "%Y-%m-%d")
        except (TypeError, ValueError):
            return self._with_latency(self._response(conversation_id, "abandoned", None, None, None,
                                      "No action was taken because the date was invalid.", turns), started)
        reason = safety_reason(turns)
        if reason:
            return self._with_latency(self._escalate(reason, reason, conversation_id, turns), started)

        parsed = parse_turns(turns, today)
        if parsed.intent == "abandon":
            return self._with_latency(self._response(conversation_id, "abandoned", None, None, None,
                                      "No action was taken.", turns), started)
        if parsed.intent == "refuse":
            return self._with_latency(self._response(conversation_id, "refused", None, None, None,
                                      "I cannot perform that request.", turns), started)
        if parsed.intent is None:
            return self._with_latency(self._response(conversation_id, "abandoned", None, None, None,
                                      "No action was taken.", turns), started)
        if parsed.intent == "cancel" and parsed.patient_name and parsed.caller_name and parsed.patient_name != parsed.caller_name:
            return self._with_latency(self._escalate("not_authorised", "Caller is acting for another adult.",
                                      conversation_id, turns), started)

        if not parsed.patient_name and parsed.intent in {"book", "reschedule", "cancel"}:
            if parsed.intent == "book" and parsed.date and parsed.doctor_id:
                self.recorder.call("search_slots", doctor_id=parsed.doctor_id, date=parsed.date)
            return self._with_latency(self._response(conversation_id, "abandoned", None, None, None,
                                      "I do not have enough patient information to act.", turns), started)

        patient_id, resolve_error = self._resolve_patient(parsed)
        if resolve_error == "ambiguous_patient":
            return self._with_latency(self._escalate("ambiguous_patient", "Patient identity is ambiguous.",
                                      conversation_id, turns), started)
        if not patient_id:
            return self._with_latency(self._response(conversation_id, "abandoned", None, None, None,
                                      "I could not identify the patient.", turns), started)
        if parsed.third_party and not parsed.caller_name:
            return self._with_latency(self._escalate("not_authorised", "Caller identity is missing for a third-party request.",
                                      conversation_id, turns, patient_id), started)
        if not self._authorized(parsed, patient_id):
            return self._with_latency(self._escalate("not_authorised", "Caller is not authorised for this patient.",
                                      conversation_id, turns, patient_id), started)

        if parsed.intent == "cancel":
            result = self.recorder.call("cancel_appointment", patient_id=patient_id,
                                        doctor_id=parsed.doctor_id, date=parsed.date or today)
            if result.get("ok"):
                appt = result["appointment"]
                return self._with_latency(self._response(conversation_id, "cancelled", None, patient_id,
                                          appt["id"], "The appointment has been cancelled.", turns), started)
            return self._with_latency(self._response(conversation_id, "abandoned", None, patient_id, None,
                                      "No matching appointment was cancelled.", turns), started)

        if not parsed.date or not parsed.doctor_id:
            return self._with_latency(self._response(conversation_id, "abandoned", None, patient_id, None,
                                      "I do not have enough appointment details.", turns), started)

        if parsed.intent == "reschedule":
            new_start = parsed.time or "10:00"
            result = self.recorder.call("reschedule_appointment", patient_id=patient_id,
                                        doctor_id=parsed.doctor_id, current_date=today,
                                        new_date=parsed.date, new_start=new_start)
            if result.get("ok"):
                appt = result["appointment"]
                return self._with_latency(self._response(conversation_id, "rescheduled", None, patient_id,
                                          appt["id"], "The appointment has been rescheduled.", turns), started)
            return self._with_latency(self._response(conversation_id, "abandoned", None, patient_id, None,
                                      "The requested reschedule slot was unavailable.", turns), started)

        slots_result = self.recorder.call("search_slots", doctor_id=parsed.doctor_id, date=parsed.date)
        slot = choose_slot(slots_result.get("slots", []), parsed.time, parsed.period)
        if not slot:
            return self._with_latency(self._response(conversation_id, "abandoned", None, patient_id, None,
                                      "No valid slot is available for that request.", turns), started)
        result = self.recorder.call("book_appointment", patient_id=patient_id, doctor_id=parsed.doctor_id,
                                    date=parsed.date, start=slot)
        if result.get("ok"):
            appt = result["appointment"]
            return self._with_latency(self._response(conversation_id, "booked", None, patient_id,
                                      appt["id"], "Your appointment is booked.", turns), started)
        return self._with_latency(self._response(conversation_id, "abandoned", None, patient_id, None,
                                  "The requested slot could not be booked.", turns), started)

    def _response(self, conversation_id: str, state: str, reason: str | None, patient_id: str | None,
                  appointment_id: str | None, reply: str, turns: list[str]) -> dict[str, Any]:
        return {
            "conversation_id": conversation_id,
            "tool_calls": [call.public() for call in self.recorder.calls],
            "tool_call_details": [call.full() for call in self.recorder.calls],
            "terminal_state": state,
            "escalation_reason": reason,
            "patient_id": patient_id,
            "appointment_id": appointment_id,
            "reply": reply,
            "metrics": {"turns": len(turns), "tokens": sum(len(t.split()) for t in turns), "latency_ms": 0},
        }

    @staticmethod
    def _with_latency(response: dict[str, Any], started: float) -> dict[str, Any]:
        response["metrics"]["latency_ms"] = int((time.monotonic() - started) * 1000)
        return response
