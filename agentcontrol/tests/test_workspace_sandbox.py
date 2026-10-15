"""The Fixer's tools must make destructive / out-of-scope actions impossible."""

import os
import sys
from pathlib import Path

import pytest

from agentcontrol.fixer.workspace import SandboxViolation, Workspace, check_writable
from demo.fixture import BUG_FILE, BUG_ORIGINAL, BUG_SEEDED, TARGET_TEST, make_buggy_copy


@pytest.fixture()
def ws(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")
    workspace = Workspace.create_from(repo, test_timeout_s=60)
    yield workspace
    workspace.cleanup()


def test_copy_is_isolated_from_source(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")
    workspace = Workspace.create_from(repo)
    try:
        assert workspace.root != repo.resolve()
        workspace.apply_patch(BUG_FILE, BUG_SEEDED, BUG_ORIGINAL)
        assert BUG_SEEDED in (repo / BUG_FILE).read_text()  # original untouched
    finally:
        workspace.cleanup()
    assert not workspace.root.exists()


def test_list_and_read(ws):
    files = ws.list_files(".")["files"]
    assert BUG_FILE in files and "tests/test_fees.py" in files
    read = ws.read_file(BUG_FILE, 1, 5)
    assert read["ok"] and read["content"].startswith("   1| ")


def test_grep_finds_bug_line(ws):
    result = ws.grep(r"days_late < policy", "src")
    assert result["ok"] and result["matches"][0]["file"] == BUG_FILE


@pytest.mark.parametrize("bad", ["../secret.txt", "/etc/passwd", "C:/Windows/win.ini", "src/../../x", ".git/config"])
def test_reads_outside_repo_rejected(ws, bad):
    result = ws.read_file(bad, 1, 0)
    assert not result["ok"]


def test_symlinks_are_not_copied(tmp_path):
    if sys.platform.startswith("win"):
        pytest.skip("symlinks need admin rights on Windows")
    repo = make_buggy_copy(tmp_path / "loanlab")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOKEN=abc")
    os.symlink(secret, repo / "src" / "leak.txt")
    workspace = Workspace.create_from(repo)
    try:
        assert not workspace.read_file("src/leak.txt", 1, 0)["ok"]
    finally:
        workspace.cleanup()


@pytest.mark.parametrize(
    "path",
    ["tests/test_fees.py", "src/loanlab/test_helpers.py", "src/conftest.py", "pyproject.toml",
     ".github/workflows/ci.yml", "README.md", "src/loanlab/data.json"],
)
def test_write_policy_rejects(path):
    with pytest.raises(SandboxViolation):
        check_writable(path)


def test_write_policy_allows_source():
    check_writable("src/loanlab/fees.py")


def test_cannot_patch_tests(ws):
    result = ws.apply_patch("tests/test_fees.py", 'Decimal("0.00")', 'Decimal("200.00")')
    assert not result["ok"] and "only allowed under src/" in result["error"]
    assert ws.diff() == ""


def test_patch_must_be_unique_and_present(ws):
    assert "not found" in ws.apply_patch(BUG_FILE, "this text is absent", "x")["error"]
    assert "occurs" in ws.apply_patch(BUG_FILE, "return round_money(ZERO)", "return 0")["error"]


def test_patch_that_breaks_syntax_is_rejected(ws):
    result = ws.apply_patch(BUG_FILE, BUG_SEEDED, "    if days_late <= policy.grace_days\n")
    assert not result["ok"] and "does not compile" in result["error"]
    assert ws.diff() == ""


def test_run_tests_rejects_options_and_non_tests(ws):
    for bad in ["--collect-only", "-k grace", "tests/test_fees.py; rm -rf /", "src/loanlab/fees.py", "../x.py"]:
        assert not ws.run_tests(bad)["ok"], bad


def test_target_fails_then_fix_passes_and_diff_is_clean(ws):
    before = ws.run_tests(TARGET_TEST)
    assert before["ok"] and not before["passed"]
    assert ws.apply_patch(BUG_FILE, BUG_SEEDED, BUG_ORIGINAL)["ok"]
    assert ws.run_tests(TARGET_TEST)["passed"]
    assert ws.run_tests("")["passed"]
    assert ws.changed_files() == [BUG_FILE]
    diff = ws.diff()
    assert diff.startswith(f"diff --git a/{BUG_FILE} b/{BUG_FILE}")
    assert "-    if days_late < policy.grace_days:" in diff
    assert "+    if days_late <= policy.grace_days:" in diff


def test_test_subprocess_gets_no_secrets(ws, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "should-not-leak")
    probe = ws.root / "tests" / "test_env_probe.py"
    probe.write_text("import os\n\ndef test_probe():\n    assert 'GOOGLE_API_KEY' not in os.environ\n")
    assert ws.run_tests("tests/test_env_probe.py")["passed"]


def test_crlf_files_keep_line_endings(tmp_path):
    repo = make_buggy_copy(tmp_path / "loanlab")
    target = repo / BUG_FILE
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    workspace = Workspace.create_from(repo)
    try:
        assert workspace.apply_patch(BUG_FILE, BUG_SEEDED, BUG_ORIGINAL)["ok"]
        data = (workspace.root / BUG_FILE).read_bytes()
        assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
        assert workspace.changed_files() == [BUG_FILE]
    finally:
        workspace.cleanup()


def test_every_call_is_logged(ws):
    ws.list_files(".")
    ws.apply_patch("tests/test_fees.py", "a", "b")
    assert [e["tool"] for e in ws.log] == ["list_files", "apply_patch"]
    assert ws.log[1]["ok"] is False
