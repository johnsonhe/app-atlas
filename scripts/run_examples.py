"""Run the rubric's three sample questions and same-model no-tools baselines.

The baseline has only the identical user question: no system prompt, no tools,
and no dataset. Results and complete traces are saved for honest comparison.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research
import store

EXAMPLES = [
    {"id": "productivity", "question": "Compare Notion, Evernote, and Todoist: what subscription and paywall complaints recur in their identified US reviews, and what do higher-rated reviews value? Cite examples and exact keyword-match counts with denominators.",
     "apps": ["1232780281", "281796108", "572688855"], "terms": ["subscription", "paywall"]},
    {"id": "entertainment", "question": "Compare Spotify and YouTube using their listings and identified US reviews. What do reviewers report about ads and paid subscriptions, where do experiences differ, and what cannot be concluded from this sample?",
     "apps": ["324684580", "544007664"], "terms": ["ads", "subscription"]},
    {"id": "accessibility", "question": "In the unattributed Mendeley pooled review corpus, investigate accessibility complaints involving screen readers, text size, and contrast. Compare keyword-match counts with denominators, read supporting and contradictory examples, and suggest research opportunities without attributing reviews to apps or categories.",
     "corpus": "pooled", "terms": ["screen reader", "font", "contrast"]},
]


async def run_one(example, base, output):
    output.mkdir(parents=True, exist_ok=True)
    print("Running", example["id"], flush=True)
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", base + "/chat/stream", json={"message": example["question"]}) as response:
            response.raise_for_status()
            done = None
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event["type"] in ("plan", "dispatch", "gap_check", "agent_end", "error"):
                    print(example["id"], event["type"], event.get("agent", ""), event.get("status", ""), flush=True)
                if event["type"] == "done":
                    done = event
    if not done:
        raise RuntimeError("Research stream did not finish")
    (output / (example["id"] + ".json")).write_text(json.dumps(done, indent=2, ensure_ascii=False))
    (output / (example["id"] + ".md")).write_text(done["result"]["response"] + "\n")
    if done["status"] != "complete":
        raise RuntimeError(f"Example {example['id']} failed: {done['status']}")
    # Precisely the same main model, no tools and no system instruction.
    baseline = await research.generate(research.MODEL, example["question"])
    expected = []
    for term in example["terms"]:
        scopes = [[aid] for aid in example.get("apps", [])] or [None]
        for ids in scopes:
            expected.append(store.review_stats(term, app_ids=ids, corpus=example.get("corpus", "identified")))
    comparison = {"id": example["id"], "question": example["question"], "model": research.MODEL,
                  "baseline_system_prompt": None, "baseline_tools": None, "baseline_answer": baseline.text,
                  "agent_answer": done["result"]["response"], "expected_count_checks": expected,
                  "status": done["status"], "researchers": done["researchers"], "elapsed_seconds": done["elapsed"],
                  "source_count": len(done["sources"]), "generated_at": datetime.now(timezone.utc).isoformat()}
    (output / (example["id"] + "-comparison.json")).write_text(json.dumps(comparison, indent=2, ensure_ascii=False))
    print("Completed", example["id"], done["elapsed"], "seconds", len(done["sources"]), "sources", flush=True)
    return comparison


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--only", choices=[x["id"] for x in EXAMPLES])
    args=parser.parse_args()
    output=store.ROOT / "examples"
    for e in EXAMPLES:
        if not args.only or e["id"] == args.only:
            await run_one(e,args.base_url,output)


if __name__ == "__main__":
    asyncio.run(main())
