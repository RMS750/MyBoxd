from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.models.entities import Movie

logger = logging.getLogger("myboxd.letterboxd")
BASE = "https://letterboxd.com"
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_MEMORY_CACHE: dict[int, tuple[datetime, dict[str, Any] | None]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _walk_for_rating(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        aggregate = value.get("aggregateRating")
        if isinstance(aggregate, dict) and aggregate.get("ratingValue") is not None:
            return aggregate
        for child in value.values():
            found = _walk_for_rating(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _walk_for_rating(child)
            if found:
                return found
    return None


def _parse_json_ld(page: str) -> dict[str, Any] | None:
    for block in _JSON_LD_RE.findall(page):
        try:
            payload = json.loads(html.unescape(block).strip())
        except (json.JSONDecodeError, TypeError):
            continue
        aggregate = _walk_for_rating(payload)
        if not aggregate:
            continue
        try:
            rating = float(aggregate.get("ratingValue"))
        except (TypeError, ValueError):
            continue
        count = aggregate.get("ratingCount") or aggregate.get("reviewCount")
        try:
            count = int(str(count).replace(",", "")) if count is not None else None
        except (TypeError, ValueError):
            count = None
        if 0.5 <= rating <= 5.0:
            return {"rating": rating, "rating_count": count}
    return None


class LetterboxdPublicService:
    """Best-effort public Letterboxd rating reader.

    Letterboxd publishes each film's weighted average in the JSON-LD on the film
    page. This is deliberately optional: recommendation requests keep working if
    Letterboxd is slow, unavailable, or changes its public markup.
    """

    def __init__(self, timeout: float = 7.0):
        self.timeout = timeout

    async def fetch_by_tmdb(self, tmdb_id: int) -> dict[str, Any] | None:
        cached = _MEMORY_CACHE.get(int(tmdb_id))
        now = _utcnow()
        if cached and now - cached[0] < timedelta(hours=24):
            return cached[1]
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=4.0),
                follow_redirects=True,
                headers={
                    "User-Agent": "MyBoxd/1.0 (+personal movie recommendation app)",
                    "Accept": "text/html,application/xhtml+xml",
                },
            ) as client:
                response = await client.get(f"{BASE}/tmdb/{int(tmdb_id)}/")
                response.raise_for_status()
                parsed = _parse_json_ld(response.text)
                if parsed:
                    parsed["url"] = str(response.url)
                _MEMORY_CACHE[int(tmdb_id)] = (now, parsed)
                return parsed
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("Letterboxd public rating unavailable tmdb_id=%s error=%s", tmdb_id, exc)
            _MEMORY_CACHE[int(tmdb_id)] = (now, None)
            return None

    @staticmethod
    def apply(movie: Movie, payload: dict[str, Any] | None) -> None:
        movie.letterboxd_updated_at = _utcnow()
        if not payload:
            return
        movie.letterboxd_rating = payload.get("rating")
        movie.letterboxd_rating_count = payload.get("rating_count")
        movie.letterboxd_url = payload.get("url")

    async def enrich_many(self, movies: list[Movie], limit: int = 12) -> int:
        candidates = [
            movie for movie in movies
            if movie.tmdb_id
            and (
                movie.letterboxd_updated_at is None
                or _utcnow() - movie.letterboxd_updated_at > timedelta(days=7)
            )
        ][:limit]
        if not candidates:
            return 0
        semaphore = asyncio.Semaphore(4)

        async def one(movie: Movie):
            async with semaphore:
                return movie, await self.fetch_by_tmdb(int(movie.tmdb_id))

        results = await asyncio.gather(*(one(movie) for movie in candidates))
        found = 0
        for movie, payload in results:
            self.apply(movie, payload)
            if payload and payload.get("rating") is not None:
                found += 1
        return found
