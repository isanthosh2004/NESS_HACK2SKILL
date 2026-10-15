"""Build the standalone `loanlab` git repo (clean commit + bug commit) and optionally push it.

    python -m demo.publish_loanlab --out ../loanlab-publish
    python -m demo.publish_loanlab --out ../loanlab-publish --remote https://github.com/<you>/loanlab.git --push

History it creates on `main`:
    1. "Initial loanlab release"                 -> all visible tests pass
    2. "Tighten late-fee grace window check"     -> the seeded bug; 1 visible test fails

The hidden tests are NOT included — they stay in this (AgentControl) repo.

Push BEFORE turning on branch protection for `main` (protection blocks direct pushes).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from demo.fixture import BUG_COMMIT_MESSAGE, CI_TEMPLATE, TARGET_TEST, apply_bug, copy_loanlab


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout.strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="empty folder to create the repo in")
    parser.add_argument("--remote", help="GitHub URL of the empty loanlab repo")
    parser.add_argument("--push", action="store_true", help="push main to --remote (uses your own git credentials)")
    args = parser.parse_args(argv)

    repo = copy_loanlab(args.out)
    workflow = repo / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(CI_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    git(repo, "init", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "Initial loanlab release")
    apply_bug(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", BUG_COMMIT_MESSAGE)
    head = git(repo, "rev-parse", "HEAD")
    print(f"loanlab repo created at {repo.resolve()}")
    print(f"HEAD (buggy commit) = {head}")
    print(f"failing visible test: {TARGET_TEST}")

    if args.remote:
        git(repo, "remote", "add", "origin", args.remote)
        if args.push:
            git(repo, "push", "-u", "origin", "main")
            print(f"pushed to {args.remote}")
        else:
            print(f"next: cd {repo} && git push -u origin main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
