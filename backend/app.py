from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .agent import Agent
from .tools import ROOT


class AgentRunRequest(BaseModel):
    conversation_id: str
    today: str
    turns: List[str] = Field(default_factory=list)


app = FastAPI(title="SwasthiQ Clinic Front Desk Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS: Dict[str, Dict[str, Any]] = {}


def run_script(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        script = json.load(handle)
    agent = Agent()
    result = agent.run(script["id"], script.get("today", "2026-10-01"), script["turns"])
    result["script"] = {
        "id": script["id"],
        "description": script.get("description"),
        "today": script.get("today"),
        "turns": script["turns"],
        "expected": script.get("expected"),
    }
    result["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


@app.post("/agent/run")
def agent_run(request: AgentRunRequest) -> Dict[str, Any]:
    result = Agent().run(request.conversation_id, request.today, request.turns)
    RUNS[request.conversation_id] = {
        **result,
        "script": {"turns": request.turns, "today": request.today},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return result


@app.get("/api/handoffs")
def handoffs() -> Dict[str, Any]:
    scripts = sorted((ROOT / "swasthhiq" / "conversations").glob("*.json"))
    results = [RUNS.get(path.stem) or run_script(path) for path in scripts]
    for result in results:
        RUNS.setdefault(result["conversation_id"], result)
    open_handoffs = [
        item for item in results
        if item["terminal_state"] == "escalated" and not item.get("resolved", False)
    ]
    return {
        "clinic": "Sunrise Clinic",
        "summary": {
            "total": len(results),
            "completed": sum(1 for item in results if item["terminal_state"] in {"booked", "rescheduled", "cancelled"}),
            "escalated": len(open_handoffs),
            "urgent": sum(1 for item in open_handoffs if item["escalation_reason"] == "clinical_urgent"),
        },
        "handoffs": open_handoffs,
        "conversations": results,
    }


@app.get("/api/conversations/{conversation_id}")
def conversation_detail(conversation_id: str) -> Dict[str, Any]:
    if conversation_id in RUNS:
        return RUNS[conversation_id]
    path = ROOT / "swasthhiq" / "conversations" / f"{conversation_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")
    result = run_script(path)
    RUNS[conversation_id] = result
    return result


@app.post("/api/handoffs/{conversation_id}/resolve")
def resolve_handoff(conversation_id: str) -> Dict[str, Any]:
    item = RUNS.get(conversation_id)
    if not item:
        item = conversation_detail(conversation_id)
    item["resolved"] = True
    return {"ok": True, "conversation_id": conversation_id}
