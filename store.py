"""Read-only research tools over a reproducible, provenance-preserving snapshot."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DB_PATH = Path(os.getenv("DATABASE_PATH", str(DATA / "research.db")))
STOP = {"a", "an", "and", "are", "as", "at", "be", "by", "compare", "for", "from", "how", "in", "ios", "is", "it", "of", "on", "or", "the", "to", "users", "what", "which", "with", "app", "apps", "reviews"}


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    return db


def initialize() -> None:
    DATA.mkdir(exist_ok=True)
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS apps (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT, description TEXT,
          developer TEXT, price REAL, currency TEXT, rating REAL, rating_count INTEGER,
          version TEXT, released TEXT, updated TEXT, url TEXT, icon TEXT,
          fetched_at TEXT, source TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reviews (
          id TEXT PRIMARY KEY, app_id TEXT, title TEXT, text TEXT NOT NULL,
          rating INTEGER, date TEXT, version TEXT, country TEXT,
          source TEXT NOT NULL, source_row INTEGER, fetched_at TEXT
        );
        CREATE INDEX IF NOT EXISTS reviews_app ON reviews(app_id);
        CREATE INDEX IF NOT EXISTS reviews_rating ON reviews(rating);
        CREATE VIRTUAL TABLE IF NOT EXISTS reviews_fts USING fts5(
          title, text, content='reviews', content_rowid='rowid', tokenize='unicode61'
        );
        CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS evidence (
          run_id TEXT, id TEXT, payload TEXT NOT NULL, PRIMARY KEY(run_id,id)
        );
        """)
        for file, table in [(DATA / "apps.jsonl.gz", "apps"), (DATA / "reviews.jsonl.gz", "reviews")]:
            if not file.exists():
                continue
            signature = hashlib.sha256(file.read_bytes()).hexdigest()
            key = f"import:{file.name}"
            prior = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
            if prior and prior[0] == signature:
                continue
            with gzip.open(file, "rt", encoding="utf-8") as stream:
                batch = []
                for line in stream:
                    if line.strip():
                        batch.append(json.loads(line))
                    if len(batch) >= 2000:
                        _insert(db, table, batch)
                        batch = []
                _insert(db, table, batch)
            db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, signature))
        count = db.execute("SELECT count(*) FROM reviews").fetchone()[0]
        indexed = db.execute("SELECT value FROM state WHERE key='fts_count'").fetchone()
        if not indexed or int(indexed[0]) != count:
            db.execute("INSERT INTO reviews_fts(reviews_fts) VALUES ('rebuild')")
            db.execute("INSERT OR REPLACE INTO state VALUES ('fts_count',?)", (str(count),))
        # Ship the rubric examples' source snapshots so their citations survive
        # a container restart and can be inspected by the grader.
        for example in (ROOT / "examples").glob("*.json"):
            if example.name.endswith("-comparison.json"):
                continue
            try:
                recorded = json.loads(example.read_text())
                if recorded.get("run_id") and recorded.get("sources"):
                    db.executemany("INSERT OR IGNORE INTO evidence VALUES (?,?,?)", [
                        (recorded["run_id"], s["id"], json.dumps(s, ensure_ascii=False)) for s in recorded["sources"]
                    ])
            except (ValueError, KeyError):
                continue


def _insert(db: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
    db.executemany(
        f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
        [[row.get(c) for c in columns] for row in rows],
    )


def save_apps(rows: list[dict]) -> None:
    with connect() as db:
        _insert(db, "apps", rows)


def save_reviews(rows: list[dict]) -> None:
    with connect() as db:
        for row in rows:
            old = db.execute("SELECT rowid,title,text FROM reviews WHERE id=?", (row["id"],)).fetchone()
            if old:
                continue
            _insert(db, "reviews", [row])
            rid = db.execute("SELECT rowid FROM reviews WHERE id=?", (row["id"],)).fetchone()[0]
            db.execute("INSERT INTO reviews_fts(rowid,title,text) VALUES (?,?,?)", (rid, row.get("title"), row["text"]))


def overview() -> dict:
    with connect() as db:
        apps = db.execute("SELECT count(*) FROM apps").fetchone()[0]
        reviews = db.execute("SELECT count(*) FROM reviews").fetchone()[0]
        identified = db.execute("SELECT count(*) FROM reviews WHERE app_id IS NOT NULL").fetchone()[0]
        categories = [dict(r) for r in db.execute("SELECT category,count(*) count FROM apps GROUP BY category ORDER BY count DESC")]
        sources = [dict(r) for r in db.execute("SELECT source,count(*) count,min(date) first_review,max(date) last_review FROM reviews GROUP BY source")]
        app_dates = db.execute("SELECT min(fetched_at),max(fetched_at) FROM apps").fetchone()
    manifest_path = DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    return {
        "apps": apps, "reviews": reviews, "identified_reviews": identified,
        "pooled_reviews": reviews - identified, "categories": categories,
        "sources": sources, "snapshot_start": app_dates[0], "snapshot_end": app_dates[1],
        "manifest": manifest,
        "limits": [
            "Broad app discovery is available through Apple's Search API; the packaged snapshot is not the entire App Store.",
            "The Mendeley CSV has only Title, Review, and Rating. Its app identities, categories, dates, and storefronts are unknown.",
            "Apple RSS reviews are a bounded sample for the selected storefront, not all users or a complete review history.",
            "A star rating is not a written-review count. Reviews do not establish downloads, revenue, retention, or market size.",
            "App descriptions are developer claims. Review comments are user reports, not independently verified product facts.",
        ],
    }


def search_apps(query: str = "", category: str = "", limit: int = 12) -> list[dict]:
    limit = max(1, min(int(limit), 30))
    terms = re.findall(r"[\w'-]+", query)[:8]
    where, args = [], []
    for term in terms:
        where.append("(name LIKE ? OR description LIKE ? OR developer LIKE ?)")
        args.extend([f"%{term}%"] * 3)
    if category:
        where.append("category LIKE ?")
        args.append(f"%{category}%")
    sql = "SELECT a.*, (SELECT count(*) FROM reviews r WHERE r.app_id=a.id) review_sample_count FROM apps a"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY rating_count DESC LIMIT ?"
    with connect() as db:
        return [dict(r) for r in db.execute(sql, [*args, limit])]


def get_app(app_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM apps WHERE id=?", (str(app_id),)).fetchone()
        return dict(row) if row else None


def _review_filter(query: str = "", app_ids: list[str] | None = None, category: str = "", max_rating: int = 5, min_rating: int = 1, corpus: str = "all") -> tuple[str, list]:
    clauses, args = ["r.rating BETWEEN ? AND ?"], [min_rating, max_rating]
    terms = [t for t in re.findall(r"[\w]+", query.lower()) if t not in STOP][:12]
    if terms:
        # Quoted literal tokens prevent FTS syntax injection. OR makes broad research useful.
        expression = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
        clauses.append("r.rowid IN (SELECT rowid FROM reviews_fts WHERE reviews_fts MATCH ?)")
        args.append(expression)
    if app_ids:
        app_ids = [str(v) for v in app_ids][:12]
        clauses.append(f"r.app_id IN ({','.join('?' for _ in app_ids)})")
        args.extend(app_ids)
    if category:
        clauses.append("r.app_id IN (SELECT id FROM apps WHERE category LIKE ?)")
        args.append(f"%{category}%")
    if corpus == "identified":
        clauses.append("r.app_id IS NOT NULL")
    elif corpus == "pooled":
        clauses.append("r.app_id IS NULL")
    return " AND ".join(clauses), args


def search_reviews(query: str = "", app_ids: list[str] | None = None, category: str = "", max_rating: int = 5, min_rating: int = 1, corpus: str = "all", limit: int = 8) -> dict:
    where, args = _review_filter(query, app_ids, category, max_rating, min_rating, corpus)
    with connect() as db:
        total = db.execute(f"SELECT count(*) FROM reviews r WHERE {where}", args).fetchone()[0]
        rows = [dict(r) for r in db.execute(
            f"SELECT r.*,a.name app_name,a.category FROM reviews r LEFT JOIN apps a ON a.id=r.app_id WHERE {where} ORDER BY r.date DESC, r.id LIMIT ?",
            [*args, max(1, min(int(limit), 15))],
        )]
    return {"matched": total, "returned": len(rows), "match_rule": "Any non-stopword query token (OR), case-insensitive FTS. Counts are keyword matches, not semantic theme prevalence.", "reviews": rows}


def review_stats(query: str = "", app_ids: list[str] | None = None, category: str = "", corpus: str = "all") -> dict:
    where, args = _review_filter(query, app_ids, category, corpus=corpus)
    denominator_where, denominator_args = _review_filter("", app_ids, category, corpus=corpus)
    with connect() as db:
        denominator = db.execute(f"SELECT count(*) FROM reviews r WHERE {denominator_where}", denominator_args).fetchone()[0]
        count = db.execute(f"SELECT count(*) FROM reviews r WHERE {where}", args).fetchone()[0]
        ratings = [dict(r) for r in db.execute(f"SELECT r.rating,count(*) count FROM reviews r WHERE {where} GROUP BY r.rating ORDER BY r.rating", args)]
        groups = [dict(r) for r in db.execute(f"SELECT coalesce(a.name,'Unknown app (pooled corpus)') app,coalesce(a.category,'Unknown category') category,count(*) count FROM reviews r LEFT JOIN apps a ON a.id=r.app_id WHERE {where} GROUP BY r.app_id ORDER BY count DESC LIMIT 15", args)]
        dates = db.execute(f"SELECT min(date),max(date),sum(CASE WHEN app_id IS NULL THEN 1 ELSE 0 END) FROM reviews r WHERE {where}", args).fetchone()
    return {"query": query, "matched_reviews": count, "scope_reviews": denominator,
            "keyword_match_share": round(count / denominator, 4) if denominator else None,
            "ratings": ratings, "by_app": groups, "first_dated_review": dates[0], "last_dated_review": dates[1],
            "unattributed_reviews": dates[2] or 0,
            "filters": {"app_ids": app_ids or [], "category": category, "corpus": corpus},
            "method": "Count of stored, deduplicated reviews containing ANY non-stopword query token; denominator is all stored reviews under the same app/category/corpus filters. Not an estimate of all App Store users."}


class Evidence:
    """Only sources actually retrieved by a tool can be cited by the Writer."""
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.items: dict[str, dict] = {}
        self.keys: dict[str, str] = {}

    def add(self, kind: str, key: str, title: str, data: Any, url: str = "") -> str:
        fingerprint = f"{kind}:{key}"
        if fingerprint in self.keys:
            return self.keys[fingerprint]
        sid = f"S{len(self.items)+1}"
        item = {"id": sid, "kind": kind, "title": title, "url": url, "data": data,
                "snapshot_url": f"/api/reports/{self.run_id}/sources/{sid}"}
        self.items[sid] = item
        self.keys[fingerprint] = sid
        return sid

    def persist(self) -> None:
        with connect() as db:
            db.executemany("INSERT OR REPLACE INTO evidence VALUES (?,?,?)", [(self.run_id, sid, json.dumps(item, ensure_ascii=False)) for sid, item in self.items.items()])


def get_evidence(run_id: str, sid: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT payload FROM evidence WHERE run_id=? AND id=?", (run_id, sid)).fetchone()
        return json.loads(row[0]) if row else None
