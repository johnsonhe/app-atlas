"""Rebuild the packaged corpus from original sources; never synthesize reviews.

uv run python scripts/build_data.py --refresh-apple
uv run python scripts/build_data.py --appgoblin-descriptions path.tsv.xz --appgoblin-metrics path.tsv.xz
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import io
import json
import lzma
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apple
import store

# Explicit, curated seed for reproducible demos, not an exhaustive/popularity-ranked census.
SEED_IDS = [324684580,363590051,544007664,835599320,389801252,284882215,447188370,1064216828,985746746,
            310633997,443904275,454638411,874139669,686449807,1232780281,572688855,281796108,904237743,
            1212616790,507874739,327630330,909319292,951937596,1010865877,1459319842,1130616675,1447330651,
            519817714,283646709,351727428,711923939,426826309,341232718,387771637,405075943,1041517543,
            570060128,829587759,379968583,546473125,469863705,736535961,571800810,493145008,401626263,
            367003839,427916203,368677368,529379082,585027354,297606951,1641486558,878577184,477128284,
            338137227,300048137,295646461,961390574,431946152,479516143,512939461,719972451,1058959277,
            302920553,545599256,429047995,284910350,284815942,284882215,375380948]
DATA = store.DATA


def download_reviews() -> Path:
    raw = DATA / "raw" / "reviews.zip"
    if raw.exists():
        return raw
    raw.parent.mkdir(parents=True, exist_ok=True)
    url = "https://data.mendeley.com/public-api/zip/75g52mjmpf/download/2"
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as response, raw.open("wb") as out:
        while chunk := response.read(1024 * 1024):
            out.write(chunk)
    return raw


def import_pooled(archive: Path) -> tuple[list[dict], dict]:
    rows, seen = [], set()
    rejected = Counter()
    with zipfile.ZipFile(archive) as z:
        member = next(n for n in z.namelist() if n.endswith("/dataset.csv"))
        with z.open(member) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace"))
            columns = reader.fieldnames
            for index, row in enumerate(reader, start=2):
                text = (row.get("Review") or "").strip()
                title = (row.get("Title") or "").strip()
                try:
                    rating = int(float(row.get("Rating", "")))
                except (ValueError, TypeError):
                    rejected["invalid_rating"] += 1
                    continue
                if not text or rating not in range(1, 6):
                    rejected["invalid_text_or_rating"] += 1
                    continue
                signature = hashlib.sha256(json.dumps([title, text, rating], ensure_ascii=False).encode()).hexdigest()
                if signature in seen:
                    rejected["exact_duplicate_title_text_rating"] += 1
                    continue
                seen.add(signature)
                rows.append({"id": f"mendeley:{index}", "app_id": None, "title": title, "text": text,
                             "rating": rating, "date": None, "version": None, "country": None,
                             "source": "Mendeley 75g52mjmpf v2", "source_row": index, "fetched_at": None})
    return rows, {"raw_columns": columns, "retained_reviews": len(rows), "rejected": dict(rejected),
                  "original_member": member, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


async def collect_apple() -> tuple[list[dict], list[dict], list]:
    apps = await apple.lookup_apps(list(dict.fromkeys(str(i) for i in SEED_IDS)))
    # Use a temporary store for collection. The final DB is rebuilt from the packaged gzip files.
    store.initialize()
    store.save_apps(apps)
    semaphore = asyncio.Semaphore(3)
    errors = []

    async def collect(app):
        async with semaphore:
            result = await apple.fetch_reviews(app["id"], pages=2)
            if result.get("errors"):
                errors.append({"app_id": app["id"], "errors": result["errors"]})
            print(f"{app['name']}: {result.get('fetched', 0)} reviews", flush=True)
            await asyncio.sleep(0.4)

    await asyncio.gather(*(collect(a) for a in apps))
    with store.connect() as db:
        reviews = [dict(r) for r in db.execute("SELECT * FROM reviews WHERE source='Apple customer-review RSS'")]
    return apps, reviews, errors


def open_tsv(path: str):
    opener = lzma.open if path.endswith(".xz") else gzip.open if path.endswith(".gz") else open
    return opener(path, "rt", encoding="utf-8-sig", errors="replace")


def import_appgoblin(descriptions_path: str | None, metrics_path: str | None) -> list[dict]:
    indexed = {}
    now = datetime.now(timezone.utc).isoformat()
    if metrics_path:
        with open_tsv(metrics_path) as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                if row.get("store", "").lower() != "ios":
                    continue
                aid = row.get("store_id", "")
                if not aid.isdigit():
                    continue
                def number(key, cast=float):
                    try:
                        return cast(row.get(key, ""))
                    except (ValueError, TypeError):
                        return None
                indexed[aid] = {"id": aid, "name": row.get("app_name", aid), "category": row.get("app_category"),
                                "description": "", "developer": row.get("developer_id"), "price": number("price"),
                                "currency": "USD", "rating": number("rating"), "rating_count": number("total_ratings", int),
                                "version": None, "released": row.get("release_date"), "updated": row.get("store_last_updated"),
                                "url": f"https://apps.apple.com/us/app/id{aid}", "icon": "", "fetched_at": now,
                                "source": "AppGoblin CC BY 4.0"}
    if descriptions_path:
        with open_tsv(descriptions_path) as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                if row.get("appstore", "").lower() != "ios":
                    continue
                aid = row.get("store_id", "")
                if aid not in indexed:
                    continue
                indexed[aid]["description"] = row.get("description", "")
    return list(indexed.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-apple", action="store_true")
    parser.add_argument("--appgoblin-descriptions")
    parser.add_argument("--appgoblin-metrics")
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    pooled, audit = import_pooled(download_reviews())
    print("Pooled corpus:", audit, flush=True)
    if args.refresh_apple:
        apps, identified, errors = asyncio.run(collect_apple())
    else:
        apps = read_jsonl(DATA / "apps.jsonl.gz")
        identified = [r for r in read_jsonl(DATA / "reviews.jsonl.gz") if r.get("app_id")]
        errors = []
    goblin = import_appgoblin(args.appgoblin_descriptions, args.appgoblin_metrics)
    by_id = {r["id"]: r for r in [*goblin, *apps]}
    apps = list(by_id.values())
    reviews = {r["id"]: r for r in [*pooled, *identified]}
    write_jsonl(DATA / "apps.jsonl.gz", apps)
    write_jsonl(DATA / "reviews.jsonl.gz", list(reviews.values()))
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(), "apps": len(apps), "reviews": len(reviews),
        "identified_reviews": len(identified), "pooled_reviews": len(pooled), "mendeley_audit": audit,
        "sources": [
            {"name": "Mendeley iOS reviews v2", "url": "https://data.mendeley.com/datasets/75g52mjmpf/2", "license": "CC BY 4.0", "status": "loaded", "attribution": "Mumrez Khan, 2025, DOI 10.17632/75g52mjmpf.2", "limitations": "Only title, text and rating are present. No app IDs, dates or categories."},
            {"name": "Apple Search / Lookup API", "url": "https://performance-partners.apple.com/search-api", "status": "loaded" if apps else "not loaded", "selection": "Explicit curated seed across categories; live keyword discovery can add apps. Not an exhaustive census."},
            {"name": "Apple customer-review RSS", "url": "https://itunes.apple.com/us/rss/customerreviews/id=324684580/sortby=mostrecent/json", "status": "loaded" if identified else "not loaded", "selection": "Up to two most-recent pages per curated seed app, US storefront; deduplicated."},
            {"name": "AppGoblin", "url": "https://appgoblin.info/free-app-datasets", "license": "CC BY 4.0", "status": "loaded" if goblin else "available to import; not loaded", "limitations": "Free account required for exports. No AppGoblin data is claimed unless imported."},
        ], "collection_errors": errors,
        "files": {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in [DATA / "apps.jsonl.gz", DATA / "reviews.jsonl.gz"]},
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    store.initialize()
    print("Built:", {k: manifest[k] for k in ("apps", "reviews", "identified_reviews", "pooled_reviews")})


if __name__ == "__main__":
    main()
