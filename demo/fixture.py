"""The loanlab demo fixture: clean code, one seeded bug, visible + hidden tests.

Usage (from the repo root):

    python -m demo.fixture verify              # prove the fixture behaves exactly as designed
    python -m demo.fixture make-buggy OUT_DIR  # copy loanlab with the bug applied (for rehearsals)

The seeded bug is a wrong comparison operator in the late-fee grace-period
check (``<=`` -> ``<``): a payment made exactly on the last grace day gets
charged a fee. It breaks exactly one visible test and exactly two hidden tests.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentcontrol.testing import run_pytest  # noqa: E402

LOANLAB_DIR = REPO_ROOT / "demo" / "loanlab"
HIDDEN_TESTS_DIR = REPO_ROOT / "demo" / "loanlab_hidden_tests"
HIDDEN_MOUNT_NAME = "_hidden_tests"

BUG_FILE = "src/loanlab/fees.py"
BUG_ORIGINAL = "    if days_late <= policy.grace_days:\n"
BUG_SEEDED = "    if days_late < policy.grace_days:\n"
BUG_COMMIT_MESSAGE = "Tighten late-fee grace window check"

# The visible test the Fixer is pointed at.
TARGET_TEST = "tests/test_fees.py::test_no_fee_on_last_day_of_grace_period"

EXPECTED_VISIBLE_FAILURES = {TARGET_TEST}
EXPECTED_HIDDEN_FAILURES = {
    f"{HIDDEN_MOUNT_NAME}/test_hidden_fees.py::test_custom_grace_period_is_inclusive",
    f"{HIDDEN_MOUNT_NAME}/test_hidden_fees.py::test_zero_grace_period_charges_from_day_one",
}

# .github is skipped: the CI workflow lives in demo/loanlab_ci.yml and is installed by publish_loanlab.py.
_IGNORE = shutil.ignore_patterns(".git", ".github", "__pycache__", ".pytest_cache", "*.pyc", "*.egg-info", ".venv")
CI_TEMPLATE = REPO_ROOT / "demo" / "loanlab_ci.yml"


def copy_loanlab(dest: Path) -> Path:
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"{dest} is not empty")
    shutil.copytree(LOANLAB_DIR, dest, ignore=_IGNORE, dirs_exist_ok=True)
    return dest


def apply_bug(repo_dir: Path) -> None:
    path = Path(repo_dir) / BUG_FILE
    text = path.read_text(encoding="utf-8")
    if text.count(BUG_ORIGINAL) != 1:
        raise RuntimeError(f"expected exactly one '{BUG_ORIGINAL.strip()}' in {BUG_FILE}")
    path.write_text(text.replace(BUG_ORIGINAL, BUG_SEEDED), encoding="utf-8")


def make_buggy_copy(dest: Path) -> Path:
    copy_loanlab(dest)
    apply_bug(dest)
    return Path(dest)


def run_hidden_tests(repo_dir: Path, timeout_s: int = 120):
    """Mount the hidden tests into a repo copy *after* the Fixer is done, run them, remove them."""
    mount = Path(repo_dir) / HIDDEN_MOUNT_NAME
    if mount.exists():
        shutil.rmtree(mount)
    shutil.copytree(HIDDEN_TESTS_DIR, mount, ignore=_IGNORE)
    try:
        return run_pytest(Path(repo_dir), [HIDDEN_MOUNT_NAME], timeout_s=timeout_s)
    finally:
        shutil.rmtree(mount, ignore_errors=True)


def verify() -> bool:
    ok = True
    with tempfile.TemporaryDirectory(prefix="loanlab-verify-") as tmp:
        clean = copy_loanlab(Path(tmp) / "clean")
        visible = run_pytest(clean, [])
        hidden = run_hidden_tests(clean)
        print(f"[clean] visible: {visible.counts}  hidden: {hidden.counts}")
        if not (visible.passed and hidden.passed):
            print("  FAIL: clean code must pass every visible and hidden test")
            print(visible.output_tail if not visible.passed else hidden.output_tail)
            ok = False
        total = sum(visible.counts.values()) + sum(hidden.counts.values())
        if total == 0:
            print("  FAIL: no tests were collected (is pytest installed?)")
            ok = False
        v, h = visible.counts.get("passed", 0), hidden.counts.get("passed", 0)
        print(f"  test count: {v} visible + {h} hidden = {total} ({100 * v // max(total, 1)}% visible)")

        buggy = make_buggy_copy(Path(tmp) / "buggy")
        visible_b = run_pytest(buggy, [])
        hidden_b = run_hidden_tests(buggy)
        print(f"[buggy] visible: {visible_b.counts}  hidden: {hidden_b.counts}")
        if set(visible_b.failed_tests) != EXPECTED_VISIBLE_FAILURES:
            print(f"  FAIL: visible failures {visible_b.failed_tests} != {sorted(EXPECTED_VISIBLE_FAILURES)}")
            ok = False
        if set(hidden_b.failed_tests) != EXPECTED_HIDDEN_FAILURES:
            print(f"  FAIL: hidden failures {hidden_b.failed_tests} != {sorted(EXPECTED_HIDDEN_FAILURES)}")
            ok = False

        visible_text = "\n".join(p.read_text(encoding="utf-8") for p in (clean / "tests").rglob("*.py"))
        for hidden_file in HIDDEN_TESTS_DIR.glob("test_*.py"):
            for line in hidden_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("def test_") and line[4:].split("(")[0] in visible_text:
                    print(f"  FAIL: hidden test name leaks into visible tests: {line}")
                    ok = False
        if "hidden" in visible_text.lower():
            print("  FAIL: visible tests mention 'hidden'")
            ok = False
    print("FIXTURE OK" if ok else "FIXTURE BROKEN")
    return ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="check clean passes everything and the bug fails exactly as designed")
    mk = sub.add_parser("make-buggy", help="write a copy of loanlab with the seeded bug applied")
    mk.add_argument("dest", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "verify":
        return 0 if verify() else 1
    path = make_buggy_copy(args.dest)
    print(f"buggy loanlab written to {path}")
    print(f"failing test to hand the Fixer: {TARGET_TEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
