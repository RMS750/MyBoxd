from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.entities import Genre, MetadataCache, Movie, MovieCast, MovieCrew, Person
from app.utils.text import normalize_title, parse_year

BASE = "https://api.themoviedb.org/3"
logger = logging.getLogger("myboxd.tmdb")
_MEMORY_CACHE: dict[str, dict[str, Any]] = {}


class TMDBUnavailable(RuntimeError):
    pass


class TMDBService:
    def __init__(self, db: Session):
        self.db = db
        self.api_key = settings.tmdb_api_key

    @property
    def enabled(self):
        return bool(self.api_key)

    @staticmethod
    def _cache_read(key: str):
        if key in _MEMORY_CACHE:
            return _MEMORY_CACHE[key]
        try:
            with SessionLocal() as cache_db:
                cached = cache_db.scalar(select(MetadataCache).where(MetadataCache.cache_key == key))
                if cached:
                    _MEMORY_CACHE[key] = cached.payload
                    return cached.payload
        except (OperationalError, IntegrityError):
            # Cache misses must never break user-facing requests.
            return None
        return None

    @staticmethod
    def _cache_write(key: str, data: dict[str, Any]):
        _MEMORY_CACHE[key] = data
        # SQLite only allows one writer at a time. Persisting a TMDB cache row
        # from a second connection while a request is preparing to update movies
        # can make that request fail with SQLITE_BUSY / "database is locked".
        # The in-memory cache is sufficient for local SQLite development; the
        # persistent cache remains enabled for PostgreSQL production deployments.
        if settings.database_url.startswith("sqlite"):
            return
        try:
            with SessionLocal() as cache_db:
                existing = cache_db.scalar(select(MetadataCache).where(MetadataCache.cache_key == key))
                if not existing:
                    cache_db.add(MetadataCache(cache_key=key, payload=data))
                else:
                    existing.payload = data
                    existing.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
                cache_db.commit()
        except (OperationalError, IntegrityError):
            # SQLite may briefly be busy while an import commits a film. The
            # in-memory cache is enough; silently skip persistent cache writes.
            pass

    async def _get(self, path: str, params: dict[str, Any] | None = None):
        if not self.enabled:
            raise TMDBUnavailable("TMDB_API_KEY is missing")
        clean_params = dict(params or {})
        key = f"tmdb:{path}:{sorted(clean_params.items())}"
        cached = self._cache_read(key)
        if cached is not None:
            return cached

        request_params = dict(clean_params)
        request_params["api_key"] = self.api_key
        last_error = None
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0)) as client:
            for attempt in range(3):
                try:
                    response = await client.get(BASE + path, params=request_params)
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit() and attempt < 2:
                            await asyncio.sleep(min(5.0, float(retry_after)))
                            continue
                    response.raise_for_status()
                    data = response.json()
                    break
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    if attempt < 2:
                        await asyncio.sleep(0.35 * (2**attempt))
            else:
                logger.warning("TMDB request failed path=%s error=%s", path, last_error)
                raise TMDBUnavailable("TMDB is temporarily unavailable") from last_error

        # Crucially, cache writes use their own tiny transaction. The old code
        # flushed cache rows through the request DB session, holding SQLite's one
        # writer lock across subsequent network calls.
        self._cache_write(key, data)
        return data

    @staticmethod
    def match_score(title: str, year: int | None, result: dict[str, Any]) -> float:
        candidates = [result.get("title") or "", result.get("original_title") or ""]
        target = normalize_title(title)
        title_score = max(
            (SequenceMatcher(None, target, normalize_title(candidate)).ratio() for candidate in candidates if candidate),
            default=0.0,
        )
        result_year = parse_year(result.get("release_date"))
        if year and result_year:
            delta = abs(year - result_year)
            year_score = 1.0 if delta == 0 else 0.45 if delta == 1 else 0.0
        elif year or result_year:
            year_score = 0.45
        else:
            year_score = 0.7
        popularity_bonus = min(0.035, math.log1p(float(result.get("vote_count") or 0)) / 260)
        return min(1.0, 0.78 * title_score + 0.22 * year_score + popularity_bonus)

    async def search_match(self, title: str, year: int | None):
        params = {"query": title, "include_adult": "false"}
        if year:
            params["year"] = year
        data = await self._get("/search/movie", params)
        results = list(data.get("results", []))
        if not results and year:
            results = list((await self._get("/search/movie", {"query": title, "include_adult": "false"})).get("results", []))
        if not results:
            return None, 0.0

        # A supplied Letterboxd year is strong identity evidence. Reject results
        # more than one year away instead of mapping a special/remake to a famous
        # similarly named title (the bug that hit Violet Evergarden).
        if year:
            plausible = [
                item for item in results
                if (parse_year(item.get("release_date")) is None or abs(int(parse_year(item.get("release_date"))) - year) <= 1)
            ]
            if plausible:
                results = plausible
            else:
                return None, 0.0

        scored = sorted(
            ((self.match_score(title, year, item), item) for item in results[:12]),
            key=lambda pair: pair[0],
            reverse=True,
        )
        score, best = scored[0]
        if len(scored) > 1 and score < 0.90 and score - scored[1][0] < 0.04:
            return None, score
        return (best, score) if score >= 0.62 else (None, score)

    async def movie_summary(self, tmdb_id: int):
        return await self._get(f"/movie/{tmdb_id}", {})

    async def movie_details(self, tmdb_id: int):
        return await self._get(f"/movie/{tmdb_id}", {"append_to_response": "credits,keywords"})

    async def reviews(self, tmdb_id: int, limit: int = 8):
        data = await self._get(f"/movie/{tmdb_id}/reviews", {"page": 1})
        rows = []
        for item in list(data.get("results", []))[:limit]:
            details = item.get("author_details") or {}
            rating = details.get("rating")
            rows.append({
                "id": item.get("id"),
                "author": item.get("author") or details.get("username") or "Anonymous",
                "username": details.get("username"),
                "avatar_path": details.get("avatar_path"),
                "rating": float(rating) if isinstance(rating, (int, float)) else None,
                "content": (item.get("content") or "").strip(),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "url": item.get("url"),
            })
        return rows

    async def discover(self, genre_ids: list[int], pages: int = 2, *, low_rated: bool = False, popular: bool = False):
        out = []
        for page in range(1, pages + 1):
            params: dict[str, Any] = {
                "include_adult": "false",
                "page": page,
                "vote_count.gte": 120,
            }
            if low_rated:
                params.update({"sort_by": "popularity.desc", "vote_average.lte": 5.8, "vote_count.gte": 250})
            elif popular:
                params["sort_by"] = "popularity.desc"
            else:
                params["sort_by"] = "vote_average.desc"
            if genre_ids:
                params["with_genres"] = "|".join(map(str, genre_ids[:6]))
            out.extend((await self._get("/discover/movie", params)).get("results", []))
        return out

    async def search(self, q: str):
        return (await self._get("/search/movie", {"query": q, "include_adult": "false"})).get("results", [])[:20]

    def _person(self, payload: dict[str, Any]):
        tmdb_id = payload.get("id")
        person = self.db.scalar(select(Person).where(Person.tmdb_id == tmdb_id)) if tmdb_id else None
        if not person:
            person = Person(tmdb_id=tmdb_id, name=payload.get("name") or "Unknown")
            self.db.add(person)
            self.db.flush()
        return person

    def apply_details(self, movie: Movie, details: dict[str, Any], confidence: float | None = None):
        tmdb_id = details.get("id") or movie.tmdb_id
        if tmdb_id:
            duplicate = self.db.scalar(
                select(Movie).where(Movie.tmdb_id == int(tmdb_id), Movie.id != movie.id)
            )
            if duplicate:
                logger.warning(
                    "Refusing duplicate TMDB assignment source_movie=%s canonical_movie=%s tmdb_id=%s",
                    movie.id,
                    duplicate.id,
                    tmdb_id,
                )
                movie.match_confidence = 0.0
                return None

        movie.tmdb_id = tmdb_id
        movie.title = details.get("title") or movie.title
        movie.original_title = details.get("original_title")
        movie.year = parse_year(details.get("release_date")) or movie.year
        movie.runtime = details.get("runtime")
        movie.overview = details.get("overview") or movie.overview
        movie.original_language = details.get("original_language")
        movie.production_countries = [x.get("name") for x in details.get("production_countries", []) if x.get("name")]
        movie.keywords = [x.get("name") for x in details.get("keywords", {}).get("keywords", []) if x.get("name")]
        movie.popularity = details.get("popularity")
        movie.vote_average = details.get("vote_average")
        movie.vote_count = details.get("vote_count")
        movie.poster_path = details.get("poster_path")
        movie.backdrop_path = details.get("backdrop_path")
        movie.collection_name = (details.get("belongs_to_collection") or {}).get("name")
        movie.match_confidence = confidence if confidence is not None else movie.match_confidence
        movie.metadata_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        genres = []
        for payload in details.get("genres", []):
            genre = self.db.scalar(select(Genre).where(Genre.tmdb_id == payload.get("id"))) or self.db.scalar(
                select(Genre).where(Genre.name == payload.get("name"))
            )
            if not genre:
                genre = Genre(tmdb_id=payload.get("id"), name=payload.get("name") or "Unknown")
                self.db.add(genre)
                self.db.flush()
            genres.append(genre)
        movie.genres = genres
        movie.cast.clear()
        movie.crew.clear()
        for payload in details.get("credits", {}).get("cast", [])[:12]:
            movie.cast.append(
                MovieCast(
                    person=self._person(payload),
                    character=payload.get("character"),
                    order=int(payload.get("order") or 999),
                )
            )
        for payload in details.get("credits", {}).get("crew", []):
            if payload.get("job") in {"Director", "Writer", "Screenplay"}:
                movie.crew.append(
                    MovieCrew(
                        person=self._person(payload),
                        job=payload.get("job") or "Crew",
                        department=payload.get("department"),
                    )
                )
        self.db.flush()
        return movie

    async def enrich_movie(self, movie: Movie):
        if movie.tmdb_id:
            try:
                return self.apply_details(movie, await self.movie_details(movie.tmdb_id), movie.match_confidence)
            except TMDBUnavailable:
                return None

        match, confidence = await self.search_match(movie.title, movie.year)
        if not match:
            movie.match_confidence = confidence
            return None

        tmdb_id = int(match["id"])
        duplicate = self.db.scalar(select(Movie).where(Movie.tmdb_id == tmdb_id, Movie.id != movie.id))
        if duplicate:
            # Mark the row as attempted rather than crashing the whole import.
            # A year-aware matcher above makes this mostly a defensive guard.
            movie.match_confidence = 0.0
            return None
        return self.apply_details(movie, await self.movie_details(tmdb_id), confidence)
