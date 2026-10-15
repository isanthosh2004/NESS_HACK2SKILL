"""Run pytest in a subprocess and parse the result.

This is the ONLY way AgentControl executes code from a repository under test:
a fixed ``python -m pytest`` command line, a hard timeout, a scrubbed
environment (no API keys / tokens leak into the repo's code), never a shell.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# Environment variables the test subprocess is allowed to inherit. Everything
# else (GOOGLE_API_KEY, GITHUB_TOKEN, cloud credentials, ...) is dropped.
_ENV_ALLOWLIST = (
    "PATH",
    "SYSTEMROOT",  # Windows needs this for Python to start
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "APPDATA",  # Windows: user site-packages (pip install --user) live under here
    "LOCALAPPDATA",
    "VIRTUAL_ENV",
    "PYTHONPATH",
    "PYTHONUSERBASE",
)

_SUMMARY_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)")
_FAILED_LINE_RE = re.compile(r"^(FAILED|ERROR) (\S+)")


@dataclass
class TestRun:
    passed: bool
    exit_code: Optional[int]
    counts: Dict[str, int]
    failed_tests: List[str]
    duration_s: float
    timed_out: bool
    output_tail: str
    command: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def scrubbed_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    if extra:
        env.update(extra)
    return env


def parse_pytest_output(output: str) -> tuple[Dict[str, int], List[str]]:
    counts: Dict[str, int] = {}
    lines = output.strip().splitlines()
    # The final summary line looks like "1 failed, 47 passed in 0.31s".
    for line in reversed(lines):
        found = _SUMMARY_RE.findall(line)
        if found:
            for num, kind in found:
                key = "errors" if kind.startswith("error") else kind
                counts[key] = counts.get(key, 0) + int(num)
            break
    failed: List[str] = []
    for line in lines:
        match = _FAILED_LINE_RE.match(line.strip())
        if match:
            test_id = match.group(2)
            if test_id not in failed:
                failed.append(test_id)
    return counts, failed


def run_pytest(
    cwd: Path,
    targets: Sequence[str] = (),
    timeout_s: int = 60,
    tail_chars: int = 4000,
) -> TestRun:
    """Run ``python -m pytest <targets>`` inside ``cwd``.

    ``targets`` must already be validated by the caller. They are passed as
    separate argv entries (never through a shell), and anything that looks like
    a pytest option (starts with ``-``) is refused here as a second guard.
    """
    for target in targets:
        if target.startswith("-"):
            raise ValueError(f"refusing pytest option-like target: {target!r}")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-rfE",
        "--color=no",
        "-p",
        "no:cacheprovider",
        # Ignore the repo's own addopts: they could change verbosity (breaking
        # result parsing) or load arbitrary plugins.
        "-o",
        "addopts=",
        *targets,
    ]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=scrubbed_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return TestRun(
            passed=False,
            exit_code=None,
            counts={},
            failed_tests=[],
            duration_s=round(time.monotonic() - started, 2),
            timed_out=True,
            output_tail=(out[-tail_chars:] + f"\n[TIMEOUT after {timeout_s}s]"),
            command=command[1:],
        )
    output = (proc.stdout or "") + (proc.stderr or "")
    counts, failed = parse_pytest_output(output)
    return TestRun(
        passed=proc.returncode == 0,
        exit_code=proc.returncode,
        counts=counts,
        failed_tests=failed,
        duration_s=round(time.monotonic() - started, 2),
        timed_out=False,
        output_tail=output[-tail_chars:],
        command=command[1:],
    )
