"""Bounded access to Apple's public Search/Lookup API and customer-review RSS feeds."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

import httpx

import store

APPLE_SEARCH = "https://itunes.apple.com/search"
APPLE_LOOKUP = "https://itunes.apple.com/lookup"
COUNTRY = re.compile(r"^[a-z]{2}$")


def normalize_app(a: dict, source: str = "Apple Search API") -> dict:
    return {"id": str(a["trackId"]), "name": a.get("trackName", "Unknown"),
            "category": a.get("primaryGenreName"), "description": a.get("description", ""),
            "developer": a.get("artistName"), "price": a.get("price"), "currency": a.get("currency"),
            "rating": a.get("averageUserRating"), "rating_count": a.get("userRatingCount"),
            "version": a.get("version"), "released": a.get("releaseDate"), "updated": a.get("currentVersionReleaseDate"),
            "url": a.get("trackViewUrl", f"https://apps.apple.com/us/app/id{a['trackId']}"),
            "icon": a.get("artworkUrl100", ""), "fetched_at": datetime.now(timezone.utc).isoformat(), "source": source}


async def discover_apps(query: str, country: str = "us", limit: int = 8) -> dict:
    if not query.strip():
        return {"error": "Provide an app name or a specific search term."}
    if not COUNTRY.fullmatch(country):
        return {"error": "Country must be a two-letter lowercase storefront code."}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(APPLE_SEARCH, params={"term": query[:150], "country": country, "entity": "software", "limit": min(limit, 20)})
        response.raise_for_status()
        rows = [normalize_app(a) for a in response.json().get("results", []) if a.get("trackId")]
    store.save_apps(rows)
    return {"apps": rows, "country": country, "query": query, "coverage": "Search results, not a complete inventory or ranking of the App Store."}


async def lookup_apps(ids: list[str], country: str = "us") -> list[dict]:
    safe = [str(i) for i in ids if str(i).isdigit()][:100]
    if not safe:
        return []
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        response = await client.get(APPLE_LOOKUP, params={"id": ",".join(safe), "country": country, "entity": "software"})
        response.raise_for_status()
    return [normalize_app(a) for a in response.json().get("results", []) if a.get("trackId")]


async def fetch_reviews(app_id: str, country: str = "us", pages: int = 2) -> dict:
    if not str(app_id).isdigit() or not COUNTRY.fullmatch(country):
        return {"error": "Use a numeric Apple app ID and a two-letter lowercase country code."}
    rows = []
    errors = []
    now = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for page in range(1, max(1, min(int(pages), 3)) + 1):
            url = f"https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
            try:
                response = await client.get(url)
                response.raise_for_status()
                entries = response.json().get("feed", {}).get("entry", [])
                if isinstance(entries, dict):
                    entries = [entries]
                if not entries:
                    break
                for e in entries:
                    if "im:rating" not in e:
                        continue
                    review_id = e.get("id", {}).get("label")
                    if not review_id:
                        continue
                    rows.append({"id": f"apple:{country}:{app_id}:{review_id}", "app_id": str(app_id),
                                 "title": e.get("title", {}).get("label", ""), "text": e.get("content", {}).get("label", ""),
                                 "rating": int(e["im:rating"]["label"]), "date": e.get("updated", {}).get("label"),
                                 "version": e.get("im:version", {}).get("label"), "country": country,
                                 "source": "Apple customer-review RSS", "source_row": None, "fetched_at": now})
                await asyncio.sleep(0.15)
            except (httpx.HTTPError, ValueError) as e:
                errors.append(f"Page {page}: {type(e).__name__}")
                break
    store.save_reviews(rows)
    return {"app_id": str(app_id), "country": country, "fetched": len({r['id'] for r in rows}),
            "pages_requested": min(pages, 3), "errors": errors,
            "coverage": "Bounded most-recent RSS sample. Missing pages or reviews are not evidence of no complaints. Samples may overlap and are deduplicated by app, storefront, and review ID."}
