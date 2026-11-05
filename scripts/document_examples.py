"""Update the root README's complete grading examples from recorded real runs."""
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store

root=store.ROOT
submission=json.loads((root/'submission.json').read_text())
base=submission.get('deploy_url','').rstrip('/')
START = '<!-- BEGIN GENERATED GRADING EXAMPLES -->'
END = '<!-- END GENERATED GRADING EXAMPLES -->'


def answer_html(text):
    """Render the answers' small Markdown subset inside GitHub HTML table cells.

    Markdown inside raw HTML tables is not parsed by GitHub. Escape source text
    first, then render only known inline formatting and http(s) citation links.
    """
    text = html.escape(text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'^#{1,6} (.+)$', r'<strong>\1</strong>', text, flags=re.M)
    return text.replace('\n', '<br>')


parts=[START,
       'These are real runs against the packaged snapshot, not invented demonstrations. The baseline uses the exact same user question and main model with **no tools and no system prompt**. Researcher calls use the smaller model documented in the README. No sample answers are placed in the agent prompts.',
       'Generated count checks are exact OR-keyword matches in stored reviews. Multiword queries match **any** non-stopword token, not the exact phrase. They are not complaint prevalence or population estimates. Full source records and tool traces are in `examples/`. The application reloads these recorded source snapshots at startup so sample citations remain inspectable.']
expected_answers = {
    'productivity': 'The sampled reviews include Evernote price-increase and upgrade-prompt complaints, Notion Apple-billing/subscription-management friction, and praise for Todoist’s free tier. Higher-rated examples value organization and customization. The exact per-app subscription/paywall keyword counts are below; they do not measure complaint rates. A paywall match can be positive feedback.',
    'entertainment': 'Both listings advertise paid benefits such as ad-free use and offline access. Retrieved reviews report ad interruptions, and paid-user examples raise concerns about interface changes or playback experiences. Distinguish these user reports from verified product behavior. The sample cannot establish actual ad loads, population sentiment, downloads, or revenue.',
    'accessibility': 'Retrieved pooled reviews include reports about screen-reader compatibility, small text, and contrast, alongside positive accessibility experiences. Count matching tokens using the denominator of 155,933 unattributed reviews. For example, screen OR reader matches 6,934 records, font matches 378, and contrast matches 36. These are keyword matches, not counts of accessibility complaints. No app/category/date attribution or retention conclusion is supported.',
}
for name in ['productivity','entertainment','accessibility']:
    comparison=json.loads((root/'examples'/f'{name}-comparison.json').read_text())
    trace=json.loads((root/'examples'/f'{name}.json').read_text())
    report=comparison['agent_answer']
    if base:
        report=report.replace('](/api/',']('+base+'/api/')
    if 'question' in trace:
        assert comparison['question'] == trace['question']
    assert comparison['agent_answer'] == trace['result']['response']
    assert comparison['baseline_system_prompt'] is None and comparison['baseline_tools'] is None
    assert comparison['baseline_answer']
    parts += [f'### {name.title()}', '**Question:** '+comparison['question'],
              f"**Actual run:** {comparison['model']}; {comparison['researchers']} researchers; {comparison['elapsed_seconds']} seconds; {comparison['source_count']} retrieved sources.",
              '**Expected answer and provenance:**',
              expected_answers[name],
              '- Cite app descriptions from `apps.jsonl.gz` for advertised features and identified Apple RSS records in `reviews.jsonl.gz` for app-specific user reports.' if name!='accessibility' else '- Describe accessibility-related user reports in the pooled Mendeley corpus. Do not invent app names, categories, dates, storefronts, or population-level rates for these records.',
              '- Include exact counts with denominators when quantifying keyword matches. A zero keyword match is not proof of no complaints.']
    table=['| App/scope | Query (any-token matching) | Matches | Stored reviews in scope |','| --- | --- | ---: | ---: |']
    for check in comparison['expected_count_checks']:
        actual = store.review_stats(check['query'], **check['filters'])
        assert (actual['matched_reviews'], actual['scope_reviews']) == (check['matched_reviews'], check['scope_reviews'])
        ids=check['filters']['app_ids']
        label=', '.join((store.get_app(i) or {}).get('name',i) for i in ids) if ids else 'Unattributed pooled Mendeley corpus'
        table.append(f"| {label} | `{check['query']}` | {check['matched_reviews']:,} | {check['scope_reviews']:,} |")
    parts.append('\n'.join(table))
    # HTML table keeps the complete answers genuinely side by side in GitHub.
    parts += ['**Complete answers, side by side:**', '<table><tr><th>Model with no tools and no system prompt</th><th>App Atlas agent</th></tr><tr><td valign="top">'+answer_html(comparison['baseline_answer'])+'</td><td valign="top">'+answer_html(report)+'</td></tr></table>',
              f'[Complete research trace and source register](examples/{name}.json) · [Baseline, agent answer, and deterministic checks](examples/{name}-comparison.json)']
    if name == 'accessibility':
        parts.append('**Exact source files and endpoint:** [`data/reviews.jsonl.gz`](data/reviews.jsonl.gz), records with `app_id: null`, preserves each original `dataset.csv` row as `source_row`. Raw ZIP member: `A Dataset of End-User Reviews from the Apple App S/dataset.csv`, from [Mendeley version 2](https://data.mendeley.com/datasets/75g52mjmpf/2). Counts come from `review_stats(query=..., corpus="pooled")` over SQLite `reviews` / `reviews_fts`. The citations in the answer link to the exact retrieved records and counting methods.')
    else:
        ids = sorted({i for check in comparison['expected_count_checks'] for i in check['filters']['app_ids']})
        links = ' · '.join(f'[{(store.get_app(i) or {}).get("name", i)} listing](https://itunes.apple.com/lookup?id={i}&country=us) / [US review feed](https://itunes.apple.com/us/rss/customerreviews/page=1/id={i}/sortby=mostrecent/json)' for i in ids)
        parts.append('**Exact source files and endpoints:** [`data/apps.jsonl.gz`](data/apps.jsonl.gz) for listings; [`data/reviews.jsonl.gz`](data/reviews.jsonl.gz) for identified reviews, filtered by the numeric app IDs below and `country="us"`. Counts come from `review_stats` over SQLite `reviews` / `reviews_fts`. The answer citations preserve the collected snapshots; live Apple feeds can change.\n\n'+links)
    claims=[*trace['report']['summary'],*[c for s in trace['report']['sections'] for c in s['claims']]]
    known={s['id'] for s in trace['sources']}
    assert all(c['sources'] and set(c['sources'])<=known for c in claims)
    assert all('agent' in c and all(k in c for k in ['name','args','result']) for c in trace['result']['tool_calls'])
    assert trace['status']=='complete'
    audits=[c['result'] for c in trace['result']['tool_calls'] if c['name']=='audit_claims']
    parts.append('**Validation:** every factual claim cites a retrieved source ID; all recorded tool calls include the agent, arguments, and result. Citation support also received an automated evidence-checking pass; inspect the sources because a model judge is not a proof of correctness.')
    if audits:
        parts.append('Evidence-checker findings are recorded in the full trace, including repairs or omitted claims.')
parts.append(END)
readme = root / 'README.md'
text = readme.read_text()
if START not in text or END not in text:
    raise ValueError('Root README must contain the grading example section markers.')
before, rest = text.split(START, 1)
_, after = rest.split(END, 1)
readme.write_text(before+'\n\n'.join(parts)+after)
print('Updated root README with 3 complete real agent/baseline comparisons and source checks.')
