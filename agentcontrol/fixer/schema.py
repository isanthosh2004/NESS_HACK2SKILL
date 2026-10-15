"""Structured Fixer output, parsed reliably by later stages (Gates, Auditor, API)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class FixStatus(str, Enum):
    FIXED = "FIXED"
    NO_FIX_FOUND = "NO_FIX_FOUND"
    NOT_REPRODUCED = "NOT_REPRODUCED"
    ERROR = "ERROR"


class FixerClaim(BaseModel):
    """What the agent says it did (arguments of its submit_result tool call)."""

    status: FixStatus
    root_cause: str = Field(default="", max_length=2000)
    files_changed: List[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=4000)

    @field_validator("status", mode="before")
    @classmethod
    def _normalise_status(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip().upper().replace(" ", "_")
            if value in ("NO_FIX", "NOFIX", "NO_FIX_FOUND"):
                return "NO_FIX_FOUND"
        return value


class FixerOutcome(BaseModel):
    """What actually happened, verified by AgentControl (not by trusting the agent)."""

    run_id: str
    status: FixStatus
    status_reason: str = ""
    target_test: Optional[str] = None
    root_cause: str = ""
    files_changed: List[str] = Field(default_factory=list)
    notes: str = ""
    diff: str = ""
    agent_claim: Optional[FixerClaim] = None
    tests_before: Optional[Dict[str, Any]] = None
    target_after: Optional[Dict[str, Any]] = None
    suite_after: Optional[Dict[str, Any]] = None
    target_test_passed: bool = False
    suite_passed: bool = False
    llm_calls: int = 0
    tool_calls: int = 0
    tool_log: List[Dict[str, Any]] = Field(default_factory=list)  # audit trail; NEVER sent to the Auditor
    model: str = ""
    duration_s: float = 0.0
    error: Optional[str] = None
