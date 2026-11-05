# Specification and verification record

Audit date: November 4, 2026 (America/New_York). Checked against all six pages of the Project 2 assignment and the supplied `wikipedia-deep-research` reference. This is the **Deep Research** path; the Text2SQL and Evals-specific requirements do not apply.

## Repository and README

- Required root files are present: `app.py`, `pyproject.toml`, `uv.lock`, `README.md`, `submission.json`.
- Submission metadata identifies `jh5102`, path `research`, and the reachable App Atlas Cloud Run URL.
- The root README contains all three exact sample queries, concrete expected findings/counts, exact source files/API endpoints, and the complete actual baseline and agent answers side by side.
- UI sample cards, the recorded baseline questions, and README queries match exactly.
- Removed the four duplicate `examples/*.md` documents. JSON traces and comparisons remain as reproducible evidence.
- `scripts/document_examples.py` updates a bounded generated section in the root README, verifies the expected counts, and produces identical content on a repeated run. HTML table citation links render as actual anchors rather than unparsed Markdown.
- README relative file links and all generated citation links were checked.

## Code and packaged data

- **17 tests passed** with `.venv/bin/python -m pytest -q` (two upstream deprecation warnings).
- `node --check static/app.js` and `git diff --check` passed.
- `uv lock --check --offline` passed: 44 packages resolved; lockfile matches the dependency specification.
- Tests cover attribution boundaries, exact counts/denominators, unknown versus zero, parameterized/literal search, deduplication, persisted source identity, concurrent fresh-context dispatch, gap follow-up, clarification, Project 1 response fields, complete function responses under budget limits, and frozen existing review samples.
- Two new failure-path cases verify that an unavailable first or second citation-audit pass cannot publish an unchecked report. Reporting/audit instructions now explicitly reject qualitative frequency inferred from a few reviews, unsupported absence claims, and keyword counts interpreted as sentiment or phrase matches.
- The compressed data files match the manifest's byte sizes and SHA-256 hashes. All tracked files are below GitHub's 100 MB per-file limit; `.env` is not tracked.
- Packaged data: 69 apps, 17 categories, 6,650 identified Apple reviews, 155,933 unattributed Mendeley reviews (162,583 reviews total).

## Refreshed real-model examples

Each baseline uses the identical user question and main model (`gemini-3.5-flash`) with no tools and no system prompt. Researchers use `gemini-3.5-flash-lite`. Questions/expected answers are not injected as few-shot answers.

| Example | Elapsed | Researchers | Retrieved sources | Final cited claims |
| --- | ---: | ---: | ---: | ---: |
| Productivity | 60.19 s | 3 | 40 | 14 |
| Entertainment | 18.17 s | 4 | 39 | 13 |
| Accessibility | 28.03 s | 3 | 47 | 11 |

- Verified all **15 computed source records** against SQLite: numerators, denominators, rating distributions, per-app groups, and keyword-match shares.
- Verified all **102 retrieved review source records** against stored review identities, app attribution, rating, original CSV row, date/storefront, and text.
- Every one of the **38 factual claims** references retrieved source IDs. Claim support received the backend's model audit; model judgments are fallible, and a reviewer should inspect the preserved sources.
- Productivity reached one Researcher's 12-tool cap. Four excess requested calls received explicit budget errors; no extra data operation executed. All research dispatches completed, and the other two examples had no tool errors.
- Qualitative findings are user reports, not independently verified behavior. Multiword search uses OR among non-stopword tokens, never an exact phrase by default. Keyword counts cannot establish complaint prevalence, and pooled Mendeley records cannot be attributed to apps/categories/dates.

## Deployed verification

Live app: https://app-atlas-jh5102-773581043508.northamerica-northeast2.run.app

- Updated service revision: `app-atlas-jh5102-00003-hzs`, serving 100% of traffic.
- `/`, `/health`, `/api/overview`, and `/openapi.json` returned HTTP 200.
- All **126 refreshed example source endpoints** returned HTTP 200 and exactly matched the committed source snapshots, verifying that the grading citations survive deployment/startup.
- Cloud Run timeout: 300 seconds. Agent timeout: 270 seconds. Per-researcher turns, tool executions, and Lead follow-ups are bounded in code.
- A real deployed `/chat` investigation completed in **53.12 seconds**, returned exactly `response`, `session_id`, and `tool_calls`, and recorded 28 traced calls with agent names. All **15 final citation endpoints** returned HTTP 200. Complete output is in `output/production-smoke.json`.
- Earlier browser checks covered app search/profile, vague-input clarification, streaming reports, citation drawers, saving reports, and the minimal monochrome interface. This audit changed no frontend behavior.

## Continuous deployment

- Owner authorized the private-repository connection and automatic deployments.
- Developer Connect repository link: `projects/ieor-4570/locations/northamerica-northeast2/connections/connection-bvmnqxb/gitRepositoryLinks/johnsonhe-app-atlas`.
- Enabled Cloud Build trigger: `app-atlas-jh5102-continuous`, ID `72293ec4-7b38-444d-ad7d-06fd3d60574f`.
- Exact push branch filter: `^codex/app-atlas$`. Build configuration: `cloudbuild.yaml`; service account and substitutions: `deploy/trigger.json`.
- Each deployment labels Cloud Run with its Git commit SHA. Triggered builds and their logs are available in the Cloud Build console linked in the README.

## Remaining submission requirements

1. **Grader access is not granted.** GitHub lists only `johnsonhe` as a collaborator and zero pending invitations. The assignment's accounts are `codeboi07`, `bhuvighosh3`, `nniishhh`, and `x`. Inviting them grants third parties access to the private repository and awaits explicit owner authorization.
2. **Registration/uniqueness is unverified.** The assignment's signup-sheet export returned 401 (authentication required). Confirm the `jh5102` entry and that the dataset or question domain is unique. The linked deployment guide also requires authenticated access; its contents could not be independently checked, although the PDF's explicit deployment requirements were checked.
3. **Courseworks submission and continued availability are owner actions.** Submit the GitHub repository URL and keep Cloud Run running until grades are released.

The root README's specification audit records these as pending/unverified, not passed. The qualitative non-credit peer-review scores are left for reviewers to assess.
