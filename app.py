"""App Atlas: FastAPI UI, Project 1-compatible /chat, and live research events."""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import apple
import research
import store

ROOT = Path(__file__).parent
sessions: OrderedDict[str, list[dict]] = OrderedDict()
runs: OrderedDict[str, research.Run] = OrderedDict()
CAPACITY = asyncio.Semaphore(2)


@asynccontextmanager
async def lifespan(app):
    store.initialize()
    yield
    if research.CLIENT:
        await research.CLIENT.aio.aclose()


app = FastAPI(title="App Atlas", description="Evidence-led research across iOS apps", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=3000)
    session_id: str | None = Field(default=None, max_length=80)


class ChatResponse(BaseModel):
    # Exact field names/types from johnsonhe/surfcheck Project 1.
    response: str
    session_id: str
    tool_calls: list[dict]


@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@app.get("/")
async def index():
    return FileResponse(ROOT / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/health")
async def health():
    with store.connect() as db:
        count = db.execute("SELECT count(*) FROM reviews").fetchone()[0]
    return {"status": "ok" if count else "no_data", "reviews": count, "model": research.MODEL}


@app.get("/api/overview")
async def overview():
    return store.overview()


@app.get("/api/apps")
async def apps(q: str = Query(default="", max_length=150), category: str = Query(default="", max_length=100)):
    return {"apps": store.search_apps(q, category, limit=30)}


@app.get("/api/discover")
async def discover(q: str = Query(min_length=2, max_length=150), country: str = Query(default="us", pattern="^[a-z]{2}$")):
    try:
        return await apple.discover_apps(q, country)
    except Exception:
        raise HTTPException(502, "Apple search is temporarily unavailable. You can still explore the packaged snapshot.")


@app.get("/api/apps/{app_id}")
async def app_detail(app_id: str):
    item = store.get_app(app_id)
    if not item:
        raise HTTPException(404, "App not found in the loaded catalog.")
    return {"app": item, "reviews": store.search_reviews(app_ids=[app_id], limit=12), "statistics": store.review_stats(app_ids=[app_id])}


@app.get("/api/reports/{run_id}/sources/{source_id}")
async def evidence(run_id: str, source_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", run_id) or not re.fullmatch(r"S\d+", source_id):
        raise HTTPException(404, "Source not found.")
    item = store.get_evidence(run_id, source_id)
    if not item:
        raise HTTPException(404, "This source snapshot is no longer available on this instance. Rerun the question to retrieve current evidence.")
    return item


def prepare(request: ChatRequest) -> tuple[research.Run, list[dict]]:
    message = request.message.strip()
    if not message:
        raise HTTPException(422, "Enter a research question.")
    sid = request.session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = []
    sessions.move_to_end(sid)
    while len(sessions) > 100:
        sessions.popitem(last=False)
    history = sessions[sid][-6:]
    run = research.Run(message, sid)
    runs[run.id] = run
    while len(runs) > 60:
        key = next((k for k, r in runs.items() if r.status != "running"), None)
        if key is None:
            break
        runs.pop(key)
    return run, history


def remember(run: research.Run, result: dict):
    sessions.setdefault(run.session_id, []).extend([
        {"role": "user", "content": run.question},
        {"role": "assistant", "content": result["response"][:12000]},
    ])
    sessions[run.session_id] = sessions[run.session_id][-8:]


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        await asyncio.wait_for(CAPACITY.acquire(), timeout=5)
    except TimeoutError:
        raise HTTPException(429, "Two investigations are already running. Please retry shortly.")
    try:
        run, history = prepare(request)
        result = await research.run_research(run, history)
        remember(run, result)
        return result
    finally:
        CAPACITY.release()


@app.post("/chat/stream")
async def stream_chat(payload: ChatRequest, request: Request):
    try:
        await asyncio.wait_for(CAPACITY.acquire(), timeout=5)
    except TimeoutError:
        raise HTTPException(429, "Two investigations are already running. Please retry shortly.")
    try:
        run, history = prepare(payload)
    except Exception:
        CAPACITY.release()
        raise

    async def events():
        task = asyncio.create_task(research.run_research(run, history))
        try:
            yield "data: " + json.dumps({"type": "start", "session_id": run.session_id, "run_id": run.id}) + "\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(run.queue.get(), timeout=12)
                except TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": heartbeat\n\n"
                    continue
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event["type"] == "done":
                    result = await task
                    remember(run, result)
                    break
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            CAPACITY.release()

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/clear")
async def clear(session_id: str | None = None):
    if session_id:
        sessions.pop(session_id, None)
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), workers=1)
