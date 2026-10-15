"""Sandboxed working copy + the implementations behind the Fixer's tools.

Every tool the Fixer can call is a method here, and every method enforces its
own limits — the prompt asks the model to behave, this file makes misbehaviour
impossible:

* all paths are resolved and must stay inside the working copy (no ``..``,
  no absolute paths, no symlink escapes);
* ``apply_patch`` can only edit existing ``.py`` files under ``src/`` and never
  a test file, and the result must still compile;
* ``run_tests`` runs a fixed ``python -m pytest`` command with a timeout and a
  scrubbed environment — never a free-form shell;
* the hidden tests are never copied in, so no tool can read them.
"""

from __future__ import annotations

import difflib
import fnmatch
import re
import shutil
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from agentcontrol.testing import TestRun, run_pytest

EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules", ".mypy_cache", "_hidden_tests"}
_IGNORE_PATTERNS = shutil.ignore_patterns(*EXCLUDED_DIRS, "*.pyc", "*.egg-info")


def _copy_ignore(directory: str, names: List[str]) -> set:
    """Skip junk dirs AND every symlink: a link to e.g. ~/.ssh must never be followed into the copy."""
    ignored = set(_IGNORE_PATTERNS(directory, names))
    ignored.update(name for name in names if Path(directory, name).is_symlink())
    return ignored
TEST_FILE_PATTERNS = ("test_*.py", "*_test.py", "conftest.py")
TEST_DIR_NAMES = {"tests", "test", "testing"}
WRITABLE_ROOT = "src"

MAX_READ_LINES = 400
MAX_FILE_BYTES = 300_000
MAX_LIST_ENTRIES = 500
MAX_GREP_MATCHES = 50
MAX_PATTERN_LEN = 200
MAX_TOOL_OUTPUT_CHARS = 3000

# tests/test_x.py, tests/test_x.py::test_name, tests/test_x.py::TestClass::test_name[param-id]
_TEST_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*\.py(::[A-Za-z_][A-Za-z0-9_]*)*(\[[^\s\]]+\])?$")


class SandboxViolation(Exception):
    """A tool call tried to leave the sandbox or touch something it must not."""


def is_test_path(rel_path: str) -> bool:
    parts = PurePosixPath(rel_path).parts
    name = parts[-1] if parts else ""
    if any(fnmatch.fnmatch(name, pattern) for pattern in TEST_FILE_PATTERNS):
        return True
    return any(part in TEST_DIR_NAMES for part in parts[:-1])


def check_writable(rel_path: str) -> None:
    """Raise SandboxViolation unless ``rel_path`` is an editable source file."""
    parts = PurePosixPath(rel_path).parts
    if not parts or parts[0] != WRITABLE_ROOT:
        raise SandboxViolation(f"writes are only allowed under {WRITABLE_ROOT}/ (got {rel_path})")
    if is_test_path(rel_path):
        raise SandboxViolation(f"test files are read-only (got {rel_path})")
    if not parts[-1].endswith(".py"):
        raise SandboxViolation(f"only .py source files may be edited (got {rel_path})")


def _is_text(data: bytes) -> bool:
    return b"\x00" not in data[:8192]


class Workspace:
    def __init__(self, root: Path, test_timeout_s: int = 60, max_patch_chars: int = 4000, owns_root: bool = False):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(self.root)
        self.test_timeout_s = test_timeout_s
        self.max_patch_chars = max_patch_chars
        self.owns_root = owns_root
        self._baseline = self._snapshot()
        self.log: List[dict] = []

    # ------------------------------------------------------------------ setup
    @classmethod
    def create_from(cls, source_dir: Path, **kwargs) -> "Workspace":
        """Copy ``source_dir`` into a fresh temp directory and sandbox that copy."""
        tmp = Path(tempfile.mkdtemp(prefix="agentcontrol-ws-"))
        dest = tmp / "repo"
        shutil.copytree(Path(source_dir), dest, ignore=_copy_ignore)
        return cls(dest, owns_root=True, **kwargs)

    def cleanup(self) -> None:
        if self.owns_root:
            shutil.rmtree(self.root.parent, ignore_errors=True)

    def _iter_files(self, base: Path):
        for path in sorted(base.rglob("*")):
            rel_parts = path.relative_to(self.root).parts
            if any(part in EXCLUDED_DIRS for part in rel_parts):
                continue
            if path.is_file():
                yield path

    def _snapshot(self) -> Dict[str, str]:
        snap: Dict[str, str] = {}
        for path in self._iter_files(self.root):
            data = path.read_bytes()
            if len(data) <= MAX_FILE_BYTES and _is_text(data):
                snap[self.rel(path)] = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
        return snap

    # ------------------------------------------------------------------ paths
    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix() or "."

    def resolve(self, rel_path: str, must_exist: bool = True) -> Path:
        rel_path = (rel_path or ".").strip().replace("\\", "/")
        if "\x00" in rel_path or rel_path.startswith("/") or re.match(r"^[A-Za-z]:", rel_path):
            raise SandboxViolation(f"absolute paths are not allowed: {rel_path!r}")
        resolved = (self.root / rel_path).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise SandboxViolation(f"path escapes the repository: {rel_path!r}")
        if any(part in EXCLUDED_DIRS for part in resolved.relative_to(self.root).parts):
            raise SandboxViolation(f"path is not accessible: {rel_path!r}")
        if must_exist and not resolved.exists():
            raise FileNotFoundError(f"no such file or directory: {rel_path}")
        return resolved

    def _record(self, tool: str, args: dict, result: dict) -> dict:
        self.log.append({"t": round(time.time(), 3), "tool": tool, "args": args, "ok": result.get("ok", False),
                         "error": result.get("error")})
        return result

    def _guard(self, tool: str, args: dict, fn) -> dict:
        try:
            result = fn()
        except (SandboxViolation, FileNotFoundError, ValueError, IsADirectoryError, UnicodeDecodeError) as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return self._record(tool, args, result)

    # ------------------------------------------------------------------ tools
    def list_files(self, directory: str = ".") -> dict:
        def run():
            base = self.resolve(directory)
            if not base.is_dir():
                raise ValueError(f"not a directory: {directory}")
            files = [self.rel(p) for p in self._iter_files(base)]
            return {"ok": True, "directory": self.rel(base), "files": files[:MAX_LIST_ENTRIES],
                    "truncated": len(files) > MAX_LIST_ENTRIES}
        return self._guard("list_files", {"directory": directory}, run)

    def read_file(self, path: str, start_line: int = 1, end_line: int = 0) -> dict:
        def run():
            target = self.resolve(path)
            if not target.is_file():
                raise ValueError(f"not a file: {path}")
            data = target.read_bytes()
            if len(data) > MAX_FILE_BYTES or not _is_text(data):
                raise ValueError(f"file is binary or too large to read: {path}")
            lines = data.decode("utf-8").replace("\r\n", "\n").split("\n")
            start = max(int(start_line or 1), 1)
            end = int(end_line or 0)
            end = len(lines) if end <= 0 else min(end, len(lines))
            end = min(end, start + MAX_READ_LINES - 1)
            numbered = "\n".join(f"{n:>4}| {lines[n - 1]}" for n in range(start, end + 1))
            return {"ok": True, "path": self.rel(target), "start_line": start, "end_line": end,
                    "total_lines": len(lines), "content": numbered}
        return self._guard("read_file", {"path": path, "start_line": start_line, "end_line": end_line}, run)

    def grep(self, pattern: str, path: str = ".") -> dict:
        def run():
            if not pattern or len(pattern) > MAX_PATTERN_LEN:
                raise ValueError(f"pattern must be 1..{MAX_PATTERN_LEN} characters")
            try:
                regex = re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid regex: {exc}") from exc
            base = self.resolve(path)
            files = [base] if base.is_file() else list(self._iter_files(base))
            matches = []
            for file in files:
                data = file.read_bytes()
                if len(data) > MAX_FILE_BYTES or not _is_text(data):
                    continue
                for n, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
                    if regex.search(line):
                        matches.append({"file": self.rel(file), "line": n, "text": line.strip()[:200]})
                        if len(matches) >= MAX_GREP_MATCHES:
                            return {"ok": True, "matches": matches, "truncated": True}
            return {"ok": True, "matches": matches, "truncated": False}
        return self._guard("grep", {"pattern": pattern, "path": path}, run)

    def validate_test_id(self, test_id: str) -> str:
        test_id = (test_id or "").strip().replace("\\", "/")
        if not test_id:
            return ""
        if test_id.startswith("-") or not _TEST_ID_RE.match(test_id):
            raise ValueError(
                "test_id must look like 'tests/test_file.py' or 'tests/test_file.py::test_name' (no options)"
            )
        file_part = test_id.split("::", 1)[0]
        resolved = self.resolve(file_part)
        if not is_test_path(self.rel(resolved)):
            raise SandboxViolation(f"not a test file: {file_part}")
        return test_id

    def run_tests_raw(self, test_id: str = "") -> TestRun:
        test_id = self.validate_test_id(test_id)
        return run_pytest(self.root, [test_id] if test_id else [], timeout_s=self.test_timeout_s)

    def run_tests(self, test_id: str = "") -> dict:
        def run():
            result = self.run_tests_raw(test_id)
            return {"ok": True, "target": test_id or "(full suite)", "passed": result.passed,
                    "counts": result.counts, "failed_tests": result.failed_tests[:20],
                    "timed_out": result.timed_out, "output": result.output_tail[-MAX_TOOL_OUTPUT_CHARS:]}
        return self._guard("run_tests", {"test_id": test_id}, run)

    def apply_patch(self, path: str, old_text: str, new_text: str) -> dict:
        def run():
            target = self.resolve(path)
            rel = self.rel(target)
            check_writable(rel)
            if not target.is_file():
                raise ValueError(f"not a file: {path}")
            old = (old_text or "").replace("\r\n", "\n")
            new = (new_text or "").replace("\r\n", "\n")
            if not old:
                raise ValueError("old_text must not be empty — copy the exact lines you want to replace")
            if old == new:
                raise ValueError("new_text is identical to old_text")
            if len(new) > self.max_patch_chars:
                raise ValueError(f"replacement too large ({len(new)} > {self.max_patch_chars} chars); make a smaller edit")
            raw = target.read_bytes().decode("utf-8")
            crlf = "\r\n" in raw
            content = raw.replace("\r\n", "\n")
            count = content.count(old)
            if count == 0:
                raise ValueError("old_text was not found in the file; read the file again and copy the lines exactly")
            if count > 1:
                raise ValueError(f"old_text occurs {count} times; include more surrounding lines so it is unique")
            updated = content.replace(old, new, 1)
            try:
                compile(updated, rel, "exec")
            except SyntaxError as exc:
                raise ValueError(f"patch rejected, result does not compile: {exc}") from exc
            target.write_bytes((updated.replace("\n", "\r\n") if crlf else updated).encode("utf-8"))
            return {"ok": True, "path": rel, "message": "patch applied", "diff": self.diff_for(rel)}
        return self._guard("apply_patch", {"path": path, "old_text": old_text, "new_text": new_text}, run)

    # ------------------------------------------------------------------ results
    def _current_text(self, rel: str) -> Optional[str]:
        path = self.root / rel
        if not path.is_file():
            return None
        data = path.read_bytes()
        if not _is_text(data):
            return None
        return data.decode("utf-8", errors="replace").replace("\r\n", "\n")

    def diff_for(self, rel: str) -> str:
        before = self._baseline.get(rel)
        after = self._current_text(rel)
        if before == after:
            return ""
        a = (before or "").splitlines(keepends=True)
        b = (after or "").splitlines(keepends=True)
        body = "".join(difflib.unified_diff(a, b, fromfile=f"a/{rel}", tofile=f"b/{rel}"))
        return f"diff --git a/{rel} b/{rel}\n{body}"

    def changed_files(self) -> List[str]:
        current = self._snapshot()
        names = set(self._baseline) | set(current)
        return sorted(n for n in names if self._baseline.get(n) != current.get(n))

    def diff(self) -> str:
        """Unified diff (git-apply compatible) of everything changed since the copy was made."""
        return "".join(self.diff_for(rel) for rel in self.changed_files())
