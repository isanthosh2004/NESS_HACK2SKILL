# Manual steps — Tasks 0, 1, 2

Everything that could be written as code is already in this repo. These are the
steps a **human** has to do (account-security actions, clicks in a console, and
the reviews the build plan reserves for a person). Do them in this order.

> **Free-only setup.** The plan says Vertex AI; we use a **Gemini API key from
> Google AI Studio (free tier)** instead (`llm.provider: ai_studio` in
> `config.yaml`). Switching to Vertex later is one config line plus
> `LLM_PROVIDER=vertex` when running the setup script.

---

## A. Google Cloud (Task 0)

1. **Create the project** — <https://console.cloud.google.com/projectcreate>. Note the **project ID** (not the name).
2. **Link a billing account** (Billing → Link a billing account). Cloud Run, Firestore, Secret Manager and
   Artifact Registry need billing *enabled* even when you stay inside the free quotas. The $300 free trial works.
3. **Budget alert** — Billing → Budgets & alerts → Create budget → scope: this project →
   amount **$20** (or the ₹ equivalent), alert thresholds 50 %, 90 %, 100 %. Create a second one at **$50**.
4. **Run the setup script in Cloud Shell** (<https://shell.cloud.google.com>):
   ```bash
   git clone https://github.com/isanthosh2004/NESS_HACK2SKILL.git && cd NESS_HACK2SKILL
   PROJECT_ID=<your-project-id> bash infra/setup_gcp.sh
   ```
   It enables the APIs, creates Firestore `(default)` (Native, `asia-south1`), the artifacts bucket,
   two service accounts with least-privilege roles, and **empty** secrets `github-token` and `gemini-api-key`.
   Read the script before running it — it grants IAM roles.
5. **Gemini API key** — <https://aistudio.google.com/apikey> → *Create API key*. Put it in a **separate
   project that has NO billing** (AI Studio's default project is fine). A key in a billing-enabled project is
   charged on the paid tier. Free-tier prompts may be used by Google to improve its products — don't send real
   customer data.
6. **Store the key** (Cloud Shell, value is not echoed):
   ```bash
   read -rs -p "Gemini API key: " K && printf '%s' "$K" | gcloud secrets versions add gemini-api-key --data-file=- && unset K
   ```
7. **Fill in `config.yaml`**: `project.gcp_project_id`, `project.artifacts_bucket` (the script prints both),
   and `github.demo_repo` after step 9.

## B. GitHub (Tasks 0 + 1)

8. **Create an empty repo** named `loanlab` on GitHub (public, *no* README/.gitignore/license).
9. **Publish the demo repo** from your machine (creates 2 commits: clean release, then the seeded bug):
   ```powershell
   python -m demo.publish_loanlab --out ..\loanlab-publish --remote https://github.com/<you>/loanlab.git --push
   ```
10. **Branch protection** (only *after* step 9, it blocks direct pushes): loanlab → Settings → Branches →
    *Add branch ruleset* (or classic rule) for `main` → ✅ *Require a pull request before merging*
    (optionally ✅ *Require status checks* → `test`).
11. **Fine-grained token** — GitHub → Settings → Developer settings → Fine-grained tokens → *Generate*:
    - Repository access: **Only select repositories → loanlab**
    - Permissions: **Contents: Read and write**, **Pull requests: Read and write** (Metadata: read is automatic)
    - Expiry: 30 days. Then store it and **don't save it anywhere else**:
    ```bash
    read -rs -p "GitHub token: " T && printf '%s' "$T" | gcloud secrets versions add github-token --data-file=- && unset T
    ```

## C. Your machine (Task 2)

12. Python 3.12 + dependencies (PowerShell, in `D:\NESS_HACKATHON`):
    ```powershell
    py -3.12 -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env      # then paste GOOGLE_API_KEY=... into .env
    ```
13. **Check everything**: `python -m infra.check_setup --list` — confirms packages, config, the key, that the
    pinned model IDs exist for your key (edit `models:` in `config.yaml` if not), and the demo fixture.
14. **Offline tests** (no API calls): `python -m pytest` → all green.
15. **First real Fixer run**: `python -m agentcontrol.fixer --seed-bug -v`
    then rehearse: `python -m agentcontrol.fixer --seed-bug --repeat 5` (aim for 5/5 before demo day).
    Results land in `runs/<run_id>/result.json` and `fix.diff`.

## D. Reviews the plan reserves for a human

16. **Task 1** — confirm the seeded bug and the visible/hidden split:
    - bug: `demo/fixture.py` (`BUG_ORIGINAL` → `BUG_SEEDED`, in `src/loanlab/fees.py`, grace-period `<=` → `<`)
    - visible tests `demo/loanlab/tests/` (50) vs hidden `demo/loanlab_hidden_tests/` (28)
    - `python -m demo.fixture verify` proves: clean passes 78/78; bug fails exactly 1 visible + 2 hidden.
17. **Task 2** — read the **HARD RULES** block in `agentcontrol/fixer/prompts.py` and the enforcement in
    `agentcontrol/fixer/workspace.py` (`check_writable`, `resolve`, `validate_test_id`). This is your core
    safety claim to judges; change it deliberately.

## Notes / known deviations

- **Free tier rate limits**: one Fixer run is ~10–25 Gemini calls. `fixer.max_llm_calls` (40) caps a run, and
  429s are retried with backoff. If you hit the daily cap, switch `models.fixer` to a Flash-Lite model.
- **ADK `LoopAgent`** is used as the plan asks. Newest ADK releases mark it deprecated in favour of `Workflow`;
  it still works. If a future ADK removes it, pin `google-adk<2` in `requirements.txt`.
- The sandbox service account has no Gemini access with an AI Studio key (that key is a secret). For the
  prototype the Fixer runs inside the API service; the Cloud Run Jobs sandbox is v2.
- **Delete `demo/loanlab/.github/`** — it holds a 1-byte placeholder `ci.yml` left by a failed copy (the
  remote tools aren't allowed to write CI files on your disk, which is a good rule). The real workflow is
  `demo/loanlab_ci.yml`; `publish_loanlab.py` installs it into the published repo, and the fixture ignores
  `.github/`, so nothing breaks if you forget.
- The empty `NESS_HACK2SKILL/` sub-folder (with an empty `.git`) inside this repo looks accidental — delete it
  if nobody uses it.
