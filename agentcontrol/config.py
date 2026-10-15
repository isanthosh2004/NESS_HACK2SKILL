"""Load config.yaml (+ environment overrides + optional local .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    gcp_project_id: str
    region: str
    artifacts_bucket: str
    firestore_database: str
    llm_provider: str
    temperature: float
    fixer_model: str
    auditor_model: str
    fixer_max_iterations: int
    fixer_max_llm_calls: int
    test_timeout_s: int
    max_patch_chars: int
    github_demo_repo: str
    github_token_secret: str
    gemini_api_key_secret: str
    demo_repo_path: Path
    hidden_tests_path: Path


def _get(data: dict, dotted: str, default=None):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def load_settings(config_path: Optional[Path] = None) -> Settings:
    import yaml  # PyYAML

    load_dotenv()
    path = Path(config_path or os.environ.get("AGENTCONTROL_CONFIG", DEFAULT_CONFIG_PATH))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    env = os.environ.get
    return Settings(
        gcp_project_id=env("GOOGLE_CLOUD_PROJECT", _get(data, "project.gcp_project_id", "")),
        region=env("AGENTCONTROL_REGION", _get(data, "project.region", "asia-south1")),
        artifacts_bucket=env("AGENTCONTROL_BUCKET", _get(data, "project.artifacts_bucket", "")),
        firestore_database=_get(data, "project.firestore_database", "(default)"),
        llm_provider=env("AGENTCONTROL_LLM_PROVIDER", _get(data, "llm.provider", "ai_studio")),
        temperature=float(_get(data, "llm.temperature", 0.1)),
        fixer_model=env("AGENTCONTROL_FIXER_MODEL", _get(data, "models.fixer", "")),
        auditor_model=env("AGENTCONTROL_AUDITOR_MODEL", _get(data, "models.auditor", "")),
        fixer_max_iterations=int(_get(data, "fixer.max_iterations", 4)),
        fixer_max_llm_calls=int(_get(data, "fixer.max_llm_calls", 40)),
        test_timeout_s=int(_get(data, "fixer.test_timeout_seconds", 60)),
        max_patch_chars=int(_get(data, "fixer.max_patch_chars", 4000)),
        github_demo_repo=env("AGENTCONTROL_DEMO_REPO", _get(data, "github.demo_repo", "")),
        github_token_secret=_get(data, "github.token_secret", "github-token"),
        gemini_api_key_secret=_get(data, "gemini.api_key_secret", "gemini-api-key"),
        demo_repo_path=REPO_ROOT / _get(data, "demo.repo_path", "demo/loanlab"),
        hidden_tests_path=REPO_ROOT / _get(data, "demo.hidden_tests_path", "demo/loanlab_hidden_tests"),
    )


def configure_llm_env(settings: Settings) -> None:
    """Set the env vars google-genai / ADK read to pick AI Studio vs Vertex AI."""
    if settings.llm_provider == "ai_studio":
        if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Create a free key at https://aistudio.google.com/apikey "
                "and put it in .env (local) or Secret Manager (Cloud Run)."
            )
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
    elif settings.llm_provider == "vertex":
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.gcp_project_id)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    else:
        raise RuntimeError(f"unknown llm.provider {settings.llm_provider!r}")
