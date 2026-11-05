# App Atlas

App Atlas investigates iOS apps across categories using app listings, customer reviews, and reproducible numerical tools. It is for product researchers, independent developers, and people comparing products or exploring unmet user needs.

Ask a concrete question, such as comparing subscription feedback across competing apps. The Lead plans independent assignments, Researchers explore evidence concurrently in fresh contexts, the Lead requests follow-up research when needed, and the Writer produces a cited report. An Evidence Checker checks each claim against its citations before the report is shown.

**Live app:** [Open App Atlas](https://app-atlas-jh5102-773581043508.northamerica-northeast2.run.app). Deployment metadata: [`submission.json`](submission.json). **Path:** Deep Research (`research`). **Author:** `jh5102`.

## Use the app

1. Open **Research** and enter a question, or select one of the three sample investigations.
2. If the question is vague, answer the Lead's clarification in the same conversation.
3. Watch the agent badges and **Research activity**. Expand a tool call to inspect its actual input, output, agent, and elapsed time.
4. Click a citation to read the exact source snapshot, review identity, collection date, or counting method.
5. Save reports in this browser, export Markdown, or export the complete JSON trace and source register.

**Explore apps** browses the loaded catalog and can search Apple's US storefront live. **Data & coverage** shows actual loaded source counts, cleaning results, and limitations. A new investigation clears conversational context; data discovery remains available to the running instance.

## Data and reproducibility

The packaged snapshot contains **69 app listings across 17 categories, 6,650 identified Apple reviews, and 155,933 cleaned unattributed Mendeley reviews** (162,583 total reviews). The counts and checksums are recorded in [`data/manifest.json`](data/manifest.json). Live discovery can add apps and previously missing review samples to the running instance, so the UI reports actual loaded counts.

### Mendeley iOS reviews, version 2

- **Source:** Mumrez Khan (2025), *A Dataset of End-User Reviews from the Apple App Store for Software Evolution Research*, DOI [10.17632/75g52mjmpf.2](https://data.mendeley.com/datasets/75g52mjmpf/2).
- **License:** CC BY 4.0. Attribution is preserved in the manifest and source drawer.
- **Download:** the public **Download All** link on the source page, or `https://data.mendeley.com/public-api/zip/75g52mjmpf/download/2`.
- **Actual file:** ZIP member `A Dataset of End-User Reviews from the Apple App S/dataset.csv` has only `Title`, `Review`, and `Rating` columns. The original CSV row is retained in every normalized record, so citations can be checked against the raw source.
- **Cleaning:** the supplied file has 159,846 data rows. This differs slightly from the publisher's reported 159,854. Remove 3,877 exact duplicate title/text/rating tuples and 36 invalid ratings to retain 155,933 reviews. Keep ratings as integers 1–5 and require nonempty review text.
- **Critical limitation:** the supplied CSV does not identify apps, categories, dates, versions, countries, or reviewers. The publisher describes reviews from 84 apps, but this release cannot support app-level attribution. The application never guesses those fields. Use this corpus for pooled topic research only.
- The archive also contains an accessibility-annotated subset. This build does not load or claim to evaluate on that subset.

### Apple app listings and identified customer reviews

- **Metadata:** Apple's [Search/Lookup API](https://performance-partners.apple.com/search-api), `https://itunes.apple.com/lookup?id=APP_ID&country=us` and `https://itunes.apple.com/search?term=QUERY&entity=software&country=us`.
- **Reviews:** bounded public customer-review RSS, `https://itunes.apple.com/us/rss/customerreviews/page=1/id=APP_ID/sortby=mostrecent/json`.
- **Selection:** an explicit curated seed of apps across categories, listed in `scripts/build_data.py`. This is a practical demo sample, not an exhaustive census or random sample of the App Store.
- **Stored fields:** app ID, developer, category, description, price, rating count, version/update dates, source URLs, and collection timestamps. Identified reviews retain the app ID, review ID, rating, text, timestamp, version, and storefront. Author display names are not retained.
- **Deduplication:** app + storefront + review ID. Up to two recent pages are requested per seed app. Empty/error feeds and incomplete coverage are recorded; they do not imply the absence of user complaints.
- Runtime researchers fetch reviews only for apps/storefronts without existing identified reviews. Existing samples are not silently refreshed during comparisons.
- App descriptions are developer claims. Reviews are user reports. Rating counts are not written-review counts. Do not infer downloads, revenue, retention, market size, causal effects, or independently verified product behavior from these sources.

### AppGoblin import (optional; not loaded in this build)

The [AppGoblin exports](https://appgoblin.info/free-app-datasets) require a free account and are available under CC BY 4.0, with attribution to AppGoblin. This application supports importing their metrics and description TSVs, filtering to iOS and joining on `store_id`. No AppGoblin records are claimed unless an export is actually imported.

```sh
uv run python scripts/build_data.py \
  --appgoblin-metrics /absolute/path/appgoblin_store-apps-metrics.tsv.xz \
  --appgoblin-descriptions /absolute/path/appgoblin_descriptions.tsv.xz
```

To reproduce the standard packaged sources from the public archive and Apple feeds:

```sh
uv run python scripts/build_data.py --refresh-apple
```

This downloads the raw archive into ignored `data/raw/`, preserves original row provenance, and writes `data/apps.jsonl.gz`, `data/reviews.jsonl.gz`, and the manifest. Apple feeds change over time; rebuilding later will not necessarily reproduce the exact review samples. The committed compressed records and their SHA-256 hashes are the reproducible grading snapshot.

SQLite tables and an FTS5 index are built automatically from those compressed source records. `data/research.db` is generated and ignored; the Docker image builds it before serving traffic. All committed source files are under GitHub's 100 MB individual-file limit. No large download or account login is required at container startup.

## Architecture and rubric

| Requirement | Implementation |
| --- | --- |
| At least three agent shapes with distinct jobs | Lead, Researcher, Writer, plus an Evidence Checker, each with a separate instruction/context. |
| Parallel fan-out in one Lead turn | The Lead returns 2–4 typed research dispatches in a single model response. `dispatch()` executes all of them with `asyncio.gather`; every researcher receives a fresh message list. Actual dispatches are logged as `research` calls attributed to `Lead`. |
| Revisit evidence gaps | The Lead receives researcher findings and can dispatch up to two follow-up rounds. Six researchers total by default, with five tool turns and twelve data-tool executions per researcher. Budget-rejected calls return explicit errors. |
| Clarify vague questions | The Lead returns a clarification and no researcher dispatches for underspecified requests. The next user message includes bounded prior conversation. |
| Accurate citations | Only evidence retrieved by tools can enter the source registry. Every factual Writer claim requires source IDs. Unknown IDs are rejected/repaired. An Evidence Checker tests semantic support, and a deterministic guard prevents comparative complaint rates being inferred from unclassified keyword counts. Unsupported claims can be omitted. |
| Data beyond model memory | Exact recent review records, row identities, fresh app metadata, and computed counts/denominators. |
| Tool access | `search_apps`, `get_app`, `search_reviews`, `review_stats`, `discover_apps`, `fetch_reviews`, and `get_coverage`. No arbitrary SQL or shell execution is exposed to the model. |
| Supported synthesis and limits | Distinguish developer claims from user reports, identified reviews from unattributed ones, and keyword matching from semantic/population estimates. The report includes evidence gaps. |
| Show work / preserve Project 1 contract | `POST /chat` returns `response`, `session_id`, `tool_calls`; every tool call includes `agent`, `name`, `args`, `result`. The streaming UI uses a separate endpoint. |
| Frontend and creativity | Research workspace, parallel agent activity, expandable tool results, citation drawers, app explorer, coverage audit, saved reports, and Markdown/trace export. Responsive layout and keyboard navigation. |
| Deploy to GCP Cloud Run | Dockerfile, locked Python environment, packaged data, 300-second Cloud Run timeout, bounded agent runtime, and separate service. |

This is the **Deep Research path**. The 50-sample evaluation suite and two hill-climbing rounds belong to the separate Evals path; they are not claimed here.

## Three grader questions, expected answers, and baselines

The three UI cards are the three grading examples. **[Read the complete expected answers and same-model side-by-side comparisons](examples/README.md).** Each includes the actual no-tools/no-system-prompt baseline, the agent's answer, exact count checks, source provenance, and a complete JSON trace.

1. **Productivity:** compare subscription/paywall feedback and higher-rated experiences in Notion, Evernote, and Todoist. Expected: identify reported pricing/paywall themes, compare consistent keyword counts with sample denominators, include positive counterevidence, and avoid claiming population complaint rates. Sources: app listing records and identified US RSS review records.
2. **Entertainment:** compare Spotify and YouTube's advertised features with review reports about ads/subscriptions. Expected: separate listing promises from reported experiences, cite review examples, and admit that reviews do not establish objective ad loads, downloads, or revenue. Sources: app listings and identified US RSS reviews.
3. **Accessibility:** explore screen-reader, text-size, and contrast-related user reports in the Mendeley pooled corpus. Expected: exact keyword-match counts plus readable examples and useful follow-up questions, without inventing app/category/date attribution. Sources: original CSV row identities and `review_stats` results.

Recreate the real model comparisons (the local server must be running):

```sh
uv run python scripts/run_examples.py
uv run python scripts/document_examples.py
```

These commands incur normal model API usage. The baseline uses the same main model as the Lead/Writer, with only the identical user question. The research prompts do not contain the stored answers or these grading examples.

## Run locally

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). The Docker image uses Python 3.12.

```sh
uv sync --frozen
cp .env.example .env
gcloud auth application-default login
uv run app.py
```

Open `http://localhost:8080`. Set `GOOGLE_CLOUD_PROJECT` in `.env` to your own authorized project with Vertex AI enabled. The course configuration uses `ieor-4570` and location `global`. Alternatively, set `GEMINI_API_KEY` to use the Gemini Developer API. Keep secrets in `.env` or managed runtime secrets; never commit credentials.

Main model: `gemini-3.5-flash`. Researcher model: `gemini-3.5-flash-lite`, matching models available to the course project. Override `MODEL` and `RESEARCHER_MODEL` in the environment if access changes. The implementation uses the Google Gen AI SDK and an explicit, inspectable agent harness.

## API contract

```http
POST /chat
Content-Type: application/json

{"message":"Compare Spotify and YouTube's subscription feedback","session_id":null}
```

```json
{
  "response": "Markdown report with citations, or a clarification",
  "session_id": "server-issued UUID",
  "tool_calls": [
    {"agent":"Researcher 1","name":"search_reviews","args":{"query":"subscription"},"result":{"matched":0,"reviews":[]}}
  ]
}
```

The shown result is a shape illustration, not a claim about actual dataset counts. Responses include additional timing/status metadata inside tool calls. Sub-agent research invocations and evidence checks are included in the same `tool_calls` array.

- `POST /chat/stream` — SSE with live planning, agent activity, executed tool calls, and the final Project 1-compatible result.
- `GET /api/overview` — actual source counts, manifest, and limitations.
- `GET /api/apps?q=...&category=...` — local catalog search.
- `GET /api/discover?q=...` — live Apple app discovery.
- `GET /api/apps/{id}` — listing and bounded stored review examples.
- `GET /api/reports/{run_id}/sources/{source_id}` — exact retrieved evidence snapshot.
- `GET /health` — readiness and loaded review count.
- `/docs` — interactive API reference.

## Validation

```sh
uv run pytest -q
node --check static/app.js
```

Tests check app/category attribution boundaries, exact numerators and denominators, unknown versus zero, literal/parameterized search, duplicate ingestion, source persistence, actual concurrent dispatch, gap-triggered follow-up, clarification without fan-out, and the Project 1 response contract. Real-model reports and no-tools baselines are stored separately under `examples/`.

Model-based support checks reduce errors but are not proofs. Review the linked source records when assessing a report. Generated questions and report text are untrusted input, as are app descriptions and customer reviews. Only the bounded read/search/count tools are exposed to researchers. The frontend renders dynamic text with DOM text nodes, not raw HTML.

## Deployment

The Cloud Run service is separate from Surfcheck. All data needed for the examples ships with the image; no AppGoblin or Mendeley login is required at runtime.

```sh
gcloud run deploy app-atlas-jh5102 --source . \
  --project=ieor-4570 --region=northamerica-northeast2 \
  --memory=1Gi --cpu=1 --max-instances=1 --concurrency=4 --timeout=300 \
  --set-env-vars=GOOGLE_CLOUD_PROJECT=ieor-4570,GOOGLE_CLOUD_LOCATION=global,MODEL=gemini-3.5-flash,RESEARCHER_MODEL=gemini-3.5-flash-lite \
  --allow-unauthenticated
```

The runtime service account needs Vertex AI access (for example `roles/aiplatform.user`). The existing course runtime service account already has working access. The application caps each research run at 270 seconds and allows two simultaneous investigations per instance. Cloud Run's request timeout is 300 seconds. The single-instance cap bounds this course demo's scaling.

`scripts/gcloud_adc.py` can run a gcloud command using refreshed application-default credentials when the separate CLI login is expired. Its token remains in process memory and is passed only through the child environment, never command arguments or disk.

### Continuous deployment from GitHub

`cloudbuild.yaml` builds the Docker image, pushes to the existing regional Artifact Registry repository, and deploys this service. `deploy/trigger.json` specifies the private `johnsonhe/app-atlas` repository, branch `codex/app-atlas`, existing course GitHub connection, and existing build service account.

**Status: prepared, not activated.** Automatic approval review rejected creating a persistent Developer Connect link to the private repository because the required repository-access grant was not explicitly authorized. No alternate integration was created to bypass that restriction. After the repository owner approves that exact connection, activate with:

```sh
gcloud developer-connect connections git-repository-links create johnsonhe-app-atlas \
  --clone-uri=https://github.com/johnsonhe/app-atlas.git \
  --connection=connection-bvmnqxb --location=northamerica-northeast2 --project=ieor-4570
gcloud builds triggers import --source=deploy/trigger.json \
  --region=northamerica-northeast2 --project=ieor-4570
```

The trigger grants the existing GCP integration ongoing access to fetch the project source and deploy branch changes. It is limited to this new repository and does not modify Surfcheck. The GitHub App installation must also permit this repository.

Session histories and live-discovered records are ephemeral per Cloud Run instance. Saved reports include source snapshots in browser storage. The three committed grading examples' evidence is reloaded at startup, so their citation endpoints remain available after container restarts.

## Submission

`submission.json` contains `authors: ["jh5102"]` and `path: "research"`. Its `deploy_url` is filled only after a successful verified deployment. Submit this repository URL on Courseworks and keep the service running until grades are released. Confirm that the chosen question/domain is recorded in the course signup sheet.

This repository is private. The assignment lists `codeboi07`, `bhuvighosh3`, `nniishhh`, and `x` as grader collaborator accounts; the owner should grant the required access before submission. No collaborator invitations are sent automatically.
