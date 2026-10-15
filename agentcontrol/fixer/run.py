"""Run the Fixer end to end on a repo copy and verify its result independently.

    reproduce -> agent (ADK loop) -> verify target test -> verify full suite -> FixerOutcome

The agent's own claim ("FIXED") is recorded but never trusted: status is
decided by re-running the tests here.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from agentcontrol.fixer.agent import AgentReport
from agentcontrol.fixer.prompts import build_task_prompt
from agentcontrol.fixer.schema import FixerOutcome, FixStatus
from agentcontrol.fixer.workspace import Workspace

# agent_fn(workspace, task_prompt) -> AgentReport. Default = the real ADK/Gemini agent.
AgentFn = Callable[[Workspace, str], AgentReport]


def adk_agent_fn(settings) -> AgentFn:
    from agentcontrol.config import configure_llm_env
    from agentcontrol.fixer.agent import run_fixer_agent

    configure_llm_env(settings)

    def call(ws: Workspace, prompt: str) -> AgentReport:
        return run_fixer_agent(
            ws,
            prompt,
            model_id=settings.fixer_model,
            temperature=settings.temperature,
            max_iterations=settings.fixer_max_iterations,
            max_llm_calls=settings.fixer_max_llm_calls,
        )

    return call


def run_fixer(
    repo_dir: Path,
    target_test: Optional[str] = None,
    *,
    agent_fn: AgentFn,
    model_name: str = "",
    test_timeout_s: int = 60,
    max_patch_chars: int = 4000,
    run_id: Optional[str] = None,
) -> FixerOutcome:
    run_id = run_id or uuid.uuid4().hex[:12]
    started = time.monotonic()
    ws = Workspace.create_from(Path(repo_dir), test_timeout_s=test_timeout_s, max_patch_chars=max_patch_chars)
    outcome = FixerOutcome(run_id=run_id, status=FixStatus.ERROR, target_test=target_test, model=model_name)
    try:
        # 1. Reproduce (outside the agent, so NOT_REPRODUCED costs zero LLM calls).
        suite_before = ws.run_tests_raw("")
        if target_test:
            target_before = ws.run_tests_raw(target_test)
        else:
            target_before = suite_before
            target_test = suite_before.failed_tests[0] if suite_before.failed_tests else None
            outcome.target_test = target_test
        outcome.tests_before = {"suite": suite_before.to_dict(), "target": target_before.to_dict()}
        if target_before.timed_out:
            outcome.status_reason = "test run timed out before the fix; cannot reproduce reliably"
            return outcome
        if target_before.passed or not target_test:
            outcome.status = FixStatus.NOT_REPRODUCED
            outcome.status_reason = "the target test already passes; nothing to fix"
            return outcome

        # 2. Agent.
        prompt = build_task_prompt(target_test, target_before.output_tail, suite_before.failed_tests)
        report = agent_fn(ws, prompt)
        outcome.llm_calls = report.llm_calls
        outcome.agent_claim = report.claim
        outcome.error = report.error
        if report.claim:
            outcome.root_cause = report.claim.root_cause
            outcome.notes = report.claim.notes

        # 3. Verify independently.
        outcome.diff = ws.diff()
        outcome.files_changed = ws.changed_files()
        target_after = ws.run_tests_raw(target_test)
        suite_after = ws.run_tests_raw("")
        outcome.target_after = target_after.to_dict()
        outcome.suite_after = suite_after.to_dict()
        outcome.target_test_passed = target_after.passed
        outcome.suite_passed = suite_after.passed

        if report.error and not report.budget_exhausted and not outcome.diff:
            outcome.status = FixStatus.ERROR
            outcome.status_reason = f"agent failed: {report.error}"
        elif not outcome.diff:
            outcome.status = FixStatus.NO_FIX_FOUND
            outcome.status_reason = (
                "LLM call budget exhausted without a patch" if report.budget_exhausted
                else "agent made no changes" + (f" (agent said: {report.claim.notes[:200]})" if report.claim else "")
            )
        elif not target_after.passed:
            outcome.status = FixStatus.NO_FIX_FOUND
            outcome.status_reason = "a patch was made but the target test still fails"
        else:
            outcome.status = FixStatus.FIXED
            outcome.status_reason = "target test passes" + (
                " and full suite is green" if suite_after.passed
                else f"; full suite still has failures: {suite_after.failed_tests[:5]}"
            )
            if report.claim is None:
                outcome.status_reason += " (agent never called submit_result)"
        return outcome
    except Exception as exc:  # never leave a run without a result
        outcome.status = FixStatus.ERROR
        outcome.error = f"{type(exc).__name__}: {exc}"
        outcome.status_reason = "fixer pipeline crashed"
        return outcome
    finally:
        outcome.tool_log = list(ws.log)
        outcome.tool_calls = len(ws.log)
        outcome.duration_s = round(time.monotonic() - started, 2)
        ws.cleanup()
