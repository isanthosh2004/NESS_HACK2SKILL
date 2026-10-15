"""One-stop check that Tasks 0-2 are ready to run on this machine.

    python -m infra.check_setup            # everything, incl. 1 tiny Gemini call per pinned model
    python -m infra.check_setup --no-call  # skip the Gemini calls (no quota used)
    python -m infra.check_setup --list     # also print every model ID your key can use
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys

OK, WARN, FAIL = "\033[32mOK  \033[0m", "\033[33mWARN\033[0m", "\033[31mFAIL\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    OK, WARN, FAIL = "OK  ", "WARN", "FAIL"

problems = 0


def report(level: str, msg: str) -> None:
    global problems
    if level == FAIL:
        problems += 1
    print(f"[{level}] {msg}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-call", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)

    v = sys.version_info
    report(OK if v >= (3, 10) else FAIL, f"Python {v.major}.{v.minor} (3.12 recommended, 3.10+ required)")

    for mod, pkg in [("pydantic", "pydantic"), ("yaml", "PyYAML"), ("pytest", "pytest"),
                     ("google.genai", "google-genai"), ("google.adk", "google-adk")]:
        try:
            m = importlib.import_module(mod)
            report(OK, f"{pkg} {getattr(m, '__version__', '')}".strip())
        except ImportError:
            report(FAIL, f"{pkg} missing -> pip install -r requirements.txt")

    try:
        from agentcontrol.config import load_settings
        s = load_settings()
    except Exception as exc:
        report(FAIL, f"config.yaml could not be loaded: {exc}")
        return 1

    for name, value in [("project.gcp_project_id", s.gcp_project_id), ("project.artifacts_bucket", s.artifacts_bucket),
                        ("github.demo_repo", s.github_demo_repo)]:
        report(WARN if "REPLACE" in value or not value else OK,
               f"{name} = {value}" + (" (fill in after Task 0)" if "REPLACE" in value else ""))
    report(OK, f"models: fixer={s.fixer_model}  auditor={s.auditor_model}  provider={s.llm_provider}")
    if s.fixer_model == s.auditor_model:
        report(WARN, "Fixer and Auditor use the same model; the plan asks for different ones")

    if shutil.which("gcloud"):
        proj = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True,
                              shell=os.name == "nt").stdout.strip()
        report(OK if proj else WARN, f"gcloud active project: {proj or '(none)'}")
    else:
        report(WARN, "gcloud CLI not found locally (fine if you use Cloud Shell)")

    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if s.llm_provider == "ai_studio":
        report(OK if key else FAIL, "GOOGLE_API_KEY " + ("is set" if key else "missing -> put it in .env"))

    if key or s.llm_provider == "vertex":
        try:
            from google import genai

            from agentcontrol.config import configure_llm_env
            configure_llm_env(s)
            client = genai.Client()
            available = {m.name.split("/")[-1] for m in client.models.list()}
            if args.list:
                print("  models available to this key:\n    " + "\n    ".join(sorted(available)))
            for role, model in [("fixer", s.fixer_model), ("auditor", s.auditor_model)]:
                if model not in available:
                    report(FAIL, f"{role} model '{model}' not available to this key (run with --list)")
                    continue
                if args.no_call:
                    report(OK, f"{role} model '{model}' exists")
                    continue
                reply = client.models.generate_content(model=model, contents="Reply with exactly: OK")
                report(OK, f"{role} model '{model}' answered: {(reply.text or '').strip()[:20]!r}")
        except Exception as exc:
            report(FAIL, f"Gemini check failed: {type(exc).__name__}: {exc}")

    try:
        from demo.fixture import verify
        print("\n-- demo fixture --")
        report(OK if verify() else FAIL, "loanlab fixture (clean passes, bug fails exactly as designed)")
    except Exception as exc:
        report(FAIL, f"fixture check crashed: {exc}")

    print(f"\n{'All good.' if not problems else f'{problems} problem(s) to fix.'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
