import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app
import research
import store


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")
    store.initialize()
    apps = [
        {"id": "100", "name": "Test Notes", "category": "Productivity", "description": "Offline notes", "source": "test fixture", "rating_count": 500},
        {"id": "200", "name": "Test Music", "category": "Music", "description": "Music with ads", "source": "test fixture", "rating_count": 700},
    ]
    store.save_apps(apps)
    store.save_reviews([
        {"id": "a1", "app_id": "100", "title": "Price", "text": "The subscription is expensive", "rating": 1, "source": "test fixture", "date": "2026-01-01"},
        {"id": "a2", "app_id": "100", "title": "Useful", "text": "I love the offline notes", "rating": 5, "source": "test fixture", "date": "2026-01-02"},
        {"id": "b1", "app_id": "200", "title": "Ads", "text": "Ads interrupt the music", "rating": 2, "source": "test fixture", "date": "2026-01-03"},
        {"id": "p1", "app_id": None, "title": "Pooled", "text": "Subscription price is too high", "rating": 1, "source": "test fixture", "source_row": 2},
    ])
    app.sessions.clear()
    app.runs.clear()
    yield


def test_app_filters_exclude_unattributed_reviews():
    result = store.search_reviews("subscription", category="Productivity")
    assert result["matched"] == 1
    assert result["reviews"][0]["app_id"] == "100"
    assert store.search_reviews("subscription", corpus="pooled")["matched"] == 1


def test_keyword_counts_use_same_scope_denominator():
    result = store.review_stats("subscription", app_ids=["100"])
    assert result["matched_reviews"] == 1
    assert result["scope_reviews"] == 2
    assert result["keyword_match_share"] == .5
    assert result["unattributed_reviews"] == 0


def test_empty_scope_is_unavailable_not_zero_percent():
    result = store.review_stats("subscription", app_ids=["999"])
    assert result["scope_reviews"] == 0
    assert result["keyword_match_share"] is None


def test_fts_matching_is_literal_and_sql_is_parameterized():
    assert store.search_reviews('" OR 1=1 -- subscription')["matched"] >= 1
    assert store.search_apps("'; DROP TABLE apps; --") == []
    assert store.overview()["apps"] == 2


def test_any_token_rule_is_explicit_and_counts_exactly():
    result = store.review_stats("subscription ads")
    assert result["matched_reviews"] == 3
    assert "ANY" in result["method"]


def test_repeated_feed_import_does_not_duplicate():
    store.save_reviews([{"id": "a1", "app_id": "100", "title": "Price", "text": "The subscription is expensive", "rating": 1, "source": "test fixture"}])
    assert store.overview()["reviews"] == 4
    assert store.search_reviews("subscription", app_ids=["100"])["matched"] == 1


async def test_sources_point_to_actual_record_and_persist():
    run = research.Run("Research subscription complaints", "test-session")
    result = await research.execute_tool(run, "search_reviews", {"query": "subscription", "corpus": "pooled"})
    sid = result["reviews"][0]["citation"]
    assert run.evidence.items[sid]["data"]["app_id"] is None
    assert run.evidence.items[sid]["data"]["source_row"] == 2
    run.evidence.persist()
    assert store.get_evidence(run.id, sid)["data"]["id"] == "p1"


async def test_parallel_dispatch_starts_researchers_before_any_finish(monkeypatch):
    starts, finishes = [], []
    barrier = asyncio.Event()

    async def fake_researcher(run, task, number):
        starts.append(number)
        if len(starts) == 3:
            barrier.set()
        await asyncio.wait_for(barrier.wait(), timeout=1)
        assert len(starts) == 3
        finishes.append(number)
        return {"agent": f"Researcher {number}", "findings": "Test evidence"}

    monkeypatch.setattr(research, "researcher", fake_researcher)
    run = research.Run("Compare apps", "parallel-test")
    await research.dispatch(run, [research.Task(topic=f"Task {n}", question="Read evidence") for n in range(3)], 0)
    assert len(starts) == len(finishes) == 3
    assert all(c["agent"] == "Lead" and c["name"] == "research" for c in run.tool_calls)
    assert all(c["turn"] == 0 for c in run.tool_calls)


async def test_gap_followup_is_dispatched_and_writer_gets_only_findings(monkeypatch):
    prompts = []
    async def fake_json(model, instruction, prompt, schema):
        prompts.append((schema, prompt))
        if schema is research.Plan:
            return research.Plan(scope="Notes reviews", tasks=[research.Task(topic="Pricing",question="Read complaints"),research.Task(topic="Praise",question="Read praise")])
        if schema is research.GapCheck:
            checks = sum(s is research.GapCheck for s,p in prompts)
            return research.GapCheck(covered=checks > 1, explanation="Need counterevidence" if checks==1 else "Covered", tasks=[research.Task(topic="Counterevidence",question="Read high-rated reviews")] if checks==1 else [])
        if schema is research.CitationAudit:
            return research.CitationAudit(issues=[])
        sid = next(k for k,v in current_run.evidence.items.items() if v["kind"] == "review")
        return research.Report(title="Research",summary=[research.Claim(text="A sampled reviewer reports subscription concerns.",sources=[sid])],sections=[],limitations=["This is a sample."])

    async def fake_researcher(run, task, number):
        r = await research.execute_tool(run, "search_reviews", {"query":"subscription"})
        result = {"agent":f"Researcher {number}","task":task.model_dump(),"findings":"Evidence "+r["reviews"][0]["citation"]}
        run.findings.append(result)
        return result

    monkeypatch.setattr(research,"json_model",fake_json)
    monkeypatch.setattr(research,"researcher",fake_researcher)
    current_run = research.Run("Investigate subscription complaints", "gap-test")
    result = await research.run_research(current_run,[])
    assert current_run.researchers == 3
    assert current_run.status == "complete"
    assert "](/api/reports/" in result["response"]
    writer_prompt=next(p for s,p in prompts if s is research.Report)
    import json
    assert set(json.loads(writer_prompt)) == {"question","findings","evidence"}
    json.dumps(result)  # Streaming responses must never contain opaque SDK models.


async def test_vague_question_clarifies_without_dispatch(monkeypatch):
    async def fake_json(*args):
        return research.Plan(clarification="Which category or user problem would you like to investigate?",scope="Unspecified",tasks=[])
    monkeypatch.setattr(research,"json_model",fake_json)
    run=research.Run("research apps", "clarify-test")
    result=await research.run_research(run,[])
    assert run.status == "clarification"
    assert run.researchers == 0
    assert "Which category" in result["response"]


def test_project_one_chat_contract(monkeypatch):
    async def fake_run(run,history):
        run.status="clarification"
        return {"response":"Which app or category?","session_id":run.session_id,"tool_calls":[{"agent":"Lead","name":"get_coverage","args":{},"result":{}}]}
    monkeypatch.setattr(research,"run_research",fake_run)
    with TestClient(app.app) as client:
        r=client.post('/chat',json={"message":"apps"})
        assert r.status_code==200
        assert set(r.json())=={"response","session_id","tool_calls"}
        assert r.json()["tool_calls"][0]["agent"]=="Lead"


def test_evidence_invalid_paths_and_empty_messages():
    with TestClient(app.app) as client:
        assert client.get('/api/reports/invalid/sources/S1').status_code==404
        assert client.post('/chat',json={"message":" "}).status_code==422
        assert client.post('/chat',json={"message":"x"*3001}).status_code==422
        assert client.get('/health').json()["status"]=="ok"


def test_pooled_and_identified_coverage_are_distinct():
    d=store.overview()
    assert d["reviews"]==4
    assert d["identified_reviews"]==3
    assert d["pooled_reviews"]==1


async def test_tool_budget_preserves_all_function_responses(monkeypatch):
    from google.genai import types
    turns=[]
    async def fake_generate(model, contents, **kwargs):
        turns.append(contents[:])
        if len(turns)==1:
            functions=[types.FunctionCall(name="get_coverage",args={}) for _ in range(14)]
            content=types.Content(role="model",parts=[types.Part.from_function_call(name="get_coverage",args={}) for _ in functions])
            return SimpleNamespace(candidates=[SimpleNamespace(content=content)],function_calls=functions,text="")
        assert kwargs["tools"] is not None
        assert str(kwargs["tool_config"].function_calling_config.mode).endswith("NONE")
        assert len(contents[-1].parts)==14
        content=types.Content(role="model",parts=[types.Part.from_text(text="Coverage only; question remains unanswered.")])
        return SimpleNamespace(candidates=[SimpleNamespace(content=content)],function_calls=[],text="Coverage only; question remains unanswered.")
    monkeypatch.setattr(research,"generate",fake_generate)
    run=research.Run("Research", "budget-test")
    result=await research.researcher(run,research.Task(topic="Coverage",question="Inspect data"),1)
    assert len(turns)==2
    assert len(turns[0])==1  # A fresh researcher context.
    assert sum(c["status"]=="error" for c in run.tool_calls)==2
    assert result["findings"].startswith("Coverage only")
    json.dumps(run.tool_calls)


async def test_existing_identified_samples_are_not_silently_refreshed(monkeypatch):
    with store.connect() as db:
        db.execute("UPDATE reviews SET country='us' WHERE app_id IS NOT NULL")
    async def forbidden(*args,**kwargs):
        raise AssertionError("Existing samples must remain reproducible")
    monkeypatch.setattr(research.apple,"fetch_reviews",forbidden)
    run=research.Run("Research", "freeze-test")
    result=await research.execute_tool(run,"fetch_reviews",{"app_id":"100"})
    assert result["fetched"]==0
    assert result["stored_reviews"]==2
