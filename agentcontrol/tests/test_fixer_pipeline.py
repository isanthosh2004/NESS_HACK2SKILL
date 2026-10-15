"""End-to-end Fixer pipeline with scripted (non-LLM) agents: reproduce -> agent -> independent verification."""

from agentcontrol.fixer.agent import AgentReport
from agentcontrol.fixer.run import run_fixer
from agentcontrol.fixer.schema import FixerClaim, FixStatus
from agentcontrol.fixer.scripted import cheating_fixer, honest_fixer, idle_fixer
from demo.fixture import BUG_FILE, TARGET_TEST, copy_loanlab, make_buggy_copy, run_hidden_tests


def test_honest_fix(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")
    outcome = run_fixer(repo, TARGET_TEST, agent_fn=honest_fixer)
    assert outcome.status == FixStatus.FIXED
    assert outcome.target_test_passed and outcome.suite_passed
    assert outcome.files_changed == [BUG_FILE]
    assert outcome.tests_before["target"]["passed"] is False
    assert "<=" in outcome.diff


def test_honest_fix_also_passes_hidden_tests(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")
    outcome = run_fixer(repo, TARGET_TEST, agent_fn=honest_fixer)
    patched = copy_loanlab(tmp_path / "patched")
    (patched / BUG_FILE).write_text((repo / BUG_FILE).read_text().replace(
        "if days_late < policy", "if days_late <= policy"))
    assert outcome.status == FixStatus.FIXED
    assert run_hidden_tests(patched).passed


def test_cheat_is_contained_and_caught_by_hidden_tests(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")
    outcome = run_fixer(repo, TARGET_TEST, agent_fn=cheating_fixer)
    # The test edit was refused by the sandbox ...
    assert any(e["tool"] == "apply_patch" and not e["ok"] for e in outcome.tool_log)
    assert "tests/" not in outcome.diff
    # ... the hard-code makes the visible target pass (Gates/Auditor/hidden tests must catch it later).
    assert outcome.status == FixStatus.FIXED
    assert "days_late == 5" in outcome.diff


def test_target_inferred_when_not_given(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")
    outcome = run_fixer(repo, None, agent_fn=honest_fixer)
    assert outcome.target_test == TARGET_TEST
    assert outcome.status == FixStatus.FIXED


def test_not_reproduced_skips_agent(tmp_path):
    repo = copy_loanlab(tmp_path / "clean")
    called = []
    outcome = run_fixer(repo, TARGET_TEST, agent_fn=lambda ws, p: called.append(1) or AgentReport())
    assert outcome.status == FixStatus.NOT_REPRODUCED
    assert not called


def test_budget_exhausted_is_no_fix_found(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")
    outcome = run_fixer(repo, TARGET_TEST, agent_fn=idle_fixer)
    assert outcome.status == FixStatus.NO_FIX_FOUND
    assert "budget" in outcome.status_reason


def test_agent_claim_is_not_trusted(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")

    def liar(ws, prompt):
        return AgentReport(claim=FixerClaim(status="FIXED", root_cause="trust me"))

    outcome = run_fixer(repo, TARGET_TEST, agent_fn=liar)
    assert outcome.status == FixStatus.NO_FIX_FOUND
    assert outcome.agent_claim.status == FixStatus.FIXED


def test_agent_crash_becomes_error_not_hang(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")

    def boom(ws, prompt):
        raise RuntimeError("network down")

    outcome = run_fixer(repo, TARGET_TEST, agent_fn=boom)
    assert outcome.status == FixStatus.ERROR and "network down" in outcome.error


def test_prompt_contains_target_and_output(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")
    seen = {}

    def capture(ws, prompt):
        seen["prompt"] = prompt
        return AgentReport()

    run_fixer(repo, TARGET_TEST, agent_fn=capture)
    assert TARGET_TEST in seen["prompt"] and "AssertionError" in seen["prompt"]
    assert "_hidden_tests" not in seen["prompt"]
