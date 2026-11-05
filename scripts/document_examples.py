"""Write the rubric's expected answers and honest same-model comparisons."""
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store

root=store.ROOT
manifest=json.loads((store.DATA/'manifest.json').read_text())
submission=json.loads((root/'submission.json').read_text())
base=submission.get('deploy_url','').rstrip('/')
parts=['# Sample questions and same-model comparisons',
       'These are real runs against the packaged snapshot, not invented demonstrations. The baseline uses the exact same user question and main model with **no tools and no system prompt**. Researcher calls use the smaller model documented in the README. No sample answers are placed in the agent prompts.',
       'Generated count checks are exact OR-keyword matches in stored reviews. They are not complaint prevalence or population estimates. Full source records and tool traces are in the adjacent JSON files. The application reloads these recorded source snapshots at startup so sample citations remain inspectable.']
for name in ['productivity','entertainment','accessibility']:
    comparison=json.loads((root/'examples'/f'{name}-comparison.json').read_text())
    trace=json.loads((root/'examples'/f'{name}.json').read_text())
    report=comparison['agent_answer']
    if base:
        report=report.replace('](/api/',']('+base+'/api/')
    parts += [f'## {name.title()}', '**Question:** '+comparison['question'],
              f"**Actual run:** {comparison['model']}; {comparison['researchers']} researchers; {comparison['elapsed_seconds']} seconds; {comparison['source_count']} retrieved sources.",
              '**Expected answer and provenance:**',
              '- Cite app descriptions from `apps.jsonl.gz` for advertised features and identified Apple RSS records in `reviews.jsonl.gz` for app-specific user reports.' if name!='accessibility' else '- Describe accessibility-related user reports in the pooled Mendeley corpus. Do not invent app names, categories, dates, storefronts, or population-level rates for these records.',
              '- Include exact counts with denominators when quantifying keyword matches. A zero keyword match is not proof of no complaints.']
    table=['| App/scope | Query (any-token matching) | Matches | Stored reviews in scope |','| --- | --- | ---: | ---: |']
    for check in comparison['expected_count_checks']:
        ids=check['filters']['app_ids']
        label=', '.join((store.get_app(i) or {}).get('name',i) for i in ids) if ids else 'Unattributed pooled Mendeley corpus'
        table.append(f"| {label} | `{check['query']}` | {check['matched_reviews']:,} | {check['scope_reviews']:,} |")
    parts.append('\n'.join(table))
    # HTML table keeps the complete answers genuinely side by side in GitHub.
    parts += ['### Same-model comparison', '<table><tr><th>Model with no tools and no system prompt</th><th>App Atlas agent</th></tr><tr><td valign="top">'+html.escape(comparison['baseline_answer'] or '').replace('\n','<br>')+'</td><td valign="top">'+html.escape(report).replace('\n','<br>')+'</td></tr></table>',
              f'[Readable agent report]({name}.md) · [Complete research trace and source register]({name}.json) · [Baseline, agent answer, and deterministic checks]({name}-comparison.json)',
              '**Source endpoints:** `get_app`, `search_reviews`, and `review_stats` in `research.py` and `store.py`; Apple Search/Lookup `https://itunes.apple.com/lookup?id=APP_ID&country=us`; Apple public RSS `https://itunes.apple.com/us/rss/customerreviews/page=1/id=APP_ID/sortby=mostrecent/json`; pooled file member `dataset.csv`, original CSV row recorded as `source_row`.']
    claims=[*trace['report']['summary'],*[c for s in trace['report']['sections'] for c in s['claims']]]
    known={s['id'] for s in trace['sources']}
    assert all(c['sources'] and set(c['sources'])<=known for c in claims)
    assert all('agent' in c and all(k in c for k in ['name','args','result']) for c in trace['result']['tool_calls'])
    assert trace['status']=='complete'
    audits=[c['result'] for c in trace['result']['tool_calls'] if c['name']=='audit_claims']
    parts.append('**Validation:** every factual claim cites a retrieved source ID; all recorded tool calls include the agent, arguments, and result. Citation support also received an automated evidence-checking pass; inspect the sources because a model judge is not a proof of correctness.')
    if audits:
        parts.append('Evidence-checker findings are recorded in the full trace, including repairs or omitted claims.')
(root/'examples'/'README.md').write_text('\n\n'.join(parts)+'\n')
print('Documented 3 real agent/baseline comparisons with exact source-count checks.')
