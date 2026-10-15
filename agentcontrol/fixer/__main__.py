"""Fixer CLI.

Examples (from the repo root):

  # Real Gemini agent on a fresh buggy copy of the demo repo:
  python -m agentcontrol.fixer --seed-bug

  # Rehearse 5 times and report the success rate (demo stability):
  python -m agentcontrol.fixer --seed-bug --repeat 5

  # No API key? Exercise the whole pipeline with a scripted (non-LLM) fixer:
  python -m agentcontrol.fixer --seed-bug --scripted honest
  python -m agentcontrol.fixer --seed-bug --scripted cheat

  # Any local repo + failing test:
  python -m agentcontrol.fixer --repo path/to/repo --test tests/test_x.py::test_y

Results go to runs/<run_id>/result.json and runs/<run_id>/fix.diff.
Exit code: 0 FIXED, 2 NO_FIX_FOUND, 3 NOT_REPRODUCED, 1 ERROR.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from agentcontrol.config import REPO_ROOT, load_settings
from agentcontrol.fixer.run import adk_agent_fn, run_fixer
from agentcontrol.fixer.schema import FixStatus

EXIT_CODES = {FixStatus.FIXED: 0, FixStatus.NO_FIX_FOUND: 2, FixStatus.NOT_REPRODUCED: 3, FixStatus.ERROR: 1}


def _print_outcome(outcome) -> None:
    print(f"\n=== run {outcome.run_id}: {outcome.status.value} ===")
    print(f"reason       : {outcome.status_reason}")
    print(f"target test  : {outcome.target_test}  (passes now: {outcome.target_test_passed})")
    print(f"full suite   : {'green' if outcome.suite_passed else 'NOT green'}")
    print(f"files changed: {outcome.files_changed}")
    print(f"root cause   : {outcome.root_cause or '-'}")
    print(f"llm calls    : {outcome.llm_calls}   tool calls: {outcome.tool_calls}   time: {outcome.duration_s}s")
    rejected = [e for e in outcome.tool_log if not e["ok"]]
    if rejected:
        print(f"rejected tool calls ({len(rejected)}):")
        for entry in rejected[:10]:
            print(f"  - {entry['tool']}: {entry['error']}")
    if outcome.error:
        print(f"error        : {outcome.error}")
    if outcome.diff:
        print("\n" + outcome.diff)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="repository to fix (it is copied; the original is never modified)")
    parser.add_argument("--test", help="failing test id; default = first failing test in the suite")
    parser.add_argument("--seed-bug", action="store_true", help="use a fresh copy of demo/loanlab with the seeded bug")
    parser.add_argument("--scripted", choices=["honest", "cheat", "idle"], help="use a scripted fixer instead of Gemini")
    parser.add_argument("--repeat", type=int, default=1, help="run N times and report the success rate")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "runs", help="where to write results")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    settings = load_settings()
    tmp_dir = None
    repo = args.repo
    target = args.test
    if args.seed_bug:
        from demo.fixture import TARGET_TEST, make_buggy_copy

        tmp_dir = Path(tempfile.mkdtemp(prefix="loanlab-buggy-"))
        repo = make_buggy_copy(tmp_dir / "loanlab")
        target = target or TARGET_TEST
    if repo is None:
        parser.error("give --repo PATH or --seed-bug")

    if args.scripted:
        from agentcontrol.fixer.scripted import SCRIPTED

        agent_fn, model_name = SCRIPTED[args.scripted], f"scripted:{args.scripted}"
    else:
        try:
            import google.adk  # noqa: F401
        except ImportError:
            print("Google ADK is not installed. Run:  pip install -r requirements.txt", file=sys.stderr)
            return 1
        try:
            agent_fn, model_name = adk_agent_fn(settings), settings.fixer_model
        except RuntimeError as exc:
            print(f"Setup problem: {exc}", file=sys.stderr)
            return 1

    results = []
    try:
        for i in range(max(args.repeat, 1)):
            outcome = run_fixer(repo, target, agent_fn=agent_fn, model_name=model_name,
                                test_timeout_s=settings.test_timeout_s, max_patch_chars=settings.max_patch_chars)
            run_dir = args.out / outcome.run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "result.json").write_text(outcome.model_dump_json(indent=2), encoding="utf-8")
            (run_dir / "fix.diff").write_text(outcome.diff, encoding="utf-8")
            if args.repeat > 1:
                print(f"[{i + 1}/{args.repeat}] {outcome.status.value}  llm_calls={outcome.llm_calls}  "
                      f"{outcome.duration_s}s  -> {run_dir}")
            else:
                _print_outcome(outcome)
                print(f"\nsaved: {run_dir}")
            results.append(outcome)
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if args.repeat > 1:
        fixed = sum(1 for o in results if o.status == FixStatus.FIXED and o.suite_passed)
        print(f"\nsuccess rate: {fixed}/{len(results)} fixed with a green suite")
        print(json.dumps({s.value: sum(1 for o in results if o.status == s) for s in FixStatus}))
    return EXIT_CODES[results[-1].status]


if __name__ == "__main__":
    sys.exit(main())
