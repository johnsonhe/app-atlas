# Verification record

- Automated tests: **15 passed** (`uv run pytest -q`).
- JavaScript syntax: `node --check static/app.js` passed.
- Three real-model sample investigations completed in 46.13s, 18.85s, and 40.47s. Real same-model no-tools/no-system-prompt baselines and exact count checks are in `examples/`.
- No researcher failures in the three final example runs.
- Deployed `/`, `/health`, and `/api/overview` returned HTTP 200. Deployed dataset count: 162,583 reviews.
- A real production investigation completed in 26.98s and returned the exact Project 1 fields: `response`, `session_id`, `tool_calls`. Its trace contains 23 executed calls including named Lead, Researchers, and Evidence Checker. The first three cited production source endpoints returned HTTP 200.
- Packaged citation endpoints for all three grading examples returned HTTP 200 on the deployed service.
- Browser checks: app search, app profile and review metadata, vague-input clarification, full streamed investigation, review citation drawer, saving a report, and saved-report listing. The deployed landing page was also visually checked.

Live URL: https://app-atlas-jh5102-773581043508.northamerica-northeast2.run.app

Continuous deployment is **not active**: the private-repository Developer Connect link requires explicit owner approval after automatic approval review rejected the persistent access grant. The exact proposed connection and trigger are documented in `README.md` and `deploy/trigger.json`. Grader collaborator invitations are also left for explicit owner authorization.
