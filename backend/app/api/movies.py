from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_interactions, get_weights, require_csrf
from app.database import get_db
from app.models.entities import AuthSession, Genre, Movie, User, UserMovieInteraction
from app.recommendation.hybrid_ranker import rank_movies
from app.recommendation.semantic_model import SemanticSimilarity
from app.services.serialize import movie_dict
from app.services.tmdb import TMDBService, TMDBUnavailable
from app.utils.text import normalize_title, parse_year

router = APIRouter(tags=["movies"])
IMG = "https://image.tmdb.org/t/p/"
_TMDB_GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance",
    878: "Science Fiction", 10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
}


def _transient_from_tmdb(payload: dict) -> Movie:
    tmdb_id = int(payload.get("id") or 0)
    movie = Movie(
        id=-tmdb_id,
        tmdb_id=tmdb_id,
        title=payload.get("title") or "Untitled",
        normalized_title=normalize_title(payload.get("title") or "Untitled"),
        original_title=payload.get("original_title"),
        year=parse_year(payload.get("release_date")),
        runtime=payload.get("runtime"),
        overview=payload.get("overview"),
        original_language=payload.get("original_language"),
        production_countries=[x.get("name") for x in payload.get("production_countries", []) if x.get("name")],
        keywords=[x.get("name") for x in (payload.get("keywords") or {}).get("keywords", []) if x.get("name")],
        popularity=payload.get("popularity"),
        vote_average=payload.get("vote_average"),
        vote_count=payload.get("vote_count"),
        poster_path=payload.get("poster_path"),
        backdrop_path=payload.get("backdrop_path"),
    )
    genre_payloads = payload.get("genres") or [
        {"id": genre_id, "name": _TMDB_GENRES.get(int(genre_id))}
        for genre_id in payload.get("genre_ids", [])
        if str(genre_id).isdigit()
    ]
    movie.genres = [Genre(tmdb_id=g.get("id"), name=g.get("name") or "Unknown") for g in genre_payloads if g.get("name")]
    return movie


def _tmdb_overlay(base: dict, payload: dict) -> dict:
    credits = payload.get("credits") or {}
    crew = credits.get("crew") or []
    cast = credits.get("cast") or []
    director = next((x.get("name") for x in crew if x.get("job") == "Director" and x.get("name")), None)
    genres = [x.get("name") for x in payload.get("genres", []) if x.get("name")]
    keywords = [x.get("name") for x in (payload.get("keywords") or {}).get("keywords", []) if x.get("name")]
    return {
        **base,
        "title": payload.get("title") or base.get("title"),
        "original_title": payload.get("original_title") or base.get("original_title"),
        "year": parse_year(payload.get("release_date")) or base.get("year"),
        "runtime": payload.get("runtime") if payload.get("runtime") is not None else base.get("runtime"),
        "genres": genres or base.get("genres", []),
        "director": director or base.get("director"),
        "actors": [x.get("name") for x in cast[:8] if x.get("name")] or base.get("actors", []),
        "overview": payload.get("overview") or base.get("overview"),
        "keywords": keywords or base.get("keywords", []),
        "countries": [x.get("name") for x in payload.get("production_countries", []) if x.get("name")] or base.get("countries", []),
        "language": payload.get("original_language") or base.get("language"),
        "popularity": payload.get("popularity") if payload.get("popularity") is not None else base.get("popularity"),
        "vote_average": payload.get("vote_average") if payload.get("vote_average") is not None else base.get("vote_average"),
        "vote_count": payload.get("vote_count") if payload.get("vote_count") is not None else base.get("vote_count"),
        "poster_url": f"{IMG}w500{payload.get('poster_path')}" if payload.get("poster_path") else base.get("poster_url"),
        "backdrop_url": f"{IMG}w1280{payload.get('backdrop_path')}" if payload.get("backdrop_path") else base.get("backdrop_url"),
        "collection": (payload.get("belongs_to_collection") or {}).get("name") or base.get("collection"),
    }


@router.post("/movies/enrich")
async def enrich(
    limit: int = Query(120, ge=1, le=250),
    _: AuthSession = Depends(require_csrf),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Explicit import-time enrichment only; ordinary GET pages never write metadata."""
    tmdb = TMDBService(db)
    if not tmdb.enabled:
        raise HTTPException(400, "TMDB_API_KEY is missing")

    enriched = unmatched = 0
    interactions = list(
        db.scalars(select(UserMovieInteraction).where(UserMovieInteraction.user_id == user.id)).unique().all()
    )
    pending = [
        item for item in interactions
        if item.movie.metadata_updated_at is None and item.movie.match_confidence is None
    ]
    pending.sort(
        key=lambda item: (
            item.rating is not None,
            float(item.rating or 0),
            bool(item.watched),
            int(item.rewatch_count or 0),
        ),
        reverse=True,
    )

    seen: set[int] = set()
    batch = []
    for item in pending:
        if item.movie_id in seen:
            continue
        seen.add(item.movie_id)
        batch.append(item.movie)
        if len(batch) >= limit:
            break

    warning = None
    for movie in batch:
        try:
            if await tmdb.enrich_movie(movie):
                enriched += 1
            else:
                unmatched += 1
            db.commit()
        except TMDBUnavailable as exc:
            db.rollback()
            warning = str(exc)
            break

    total = db.scalar(
        select(func.count(func.distinct(Movie.id)))
        .select_from(Movie)
        .join(UserMovieInteraction)
        .where(UserMovieInteraction.user_id == user.id)
    ) or 0
    enriched_total = db.scalar(
        select(func.count(func.distinct(Movie.id)))
        .select_from(Movie)
        .join(UserMovieInteraction)
        .where(UserMovieInteraction.user_id == user.id, Movie.metadata_updated_at.is_not(None))
    ) or 0
    remaining = db.scalar(
        select(func.count(func.distinct(Movie.id)))
        .select_from(Movie)
        .join(UserMovieInteraction)
        .where(
            UserMovieInteraction.user_id == user.id,
            Movie.metadata_updated_at.is_(None),
            Movie.match_confidence.is_(None),
        )
    ) or 0
    unmatched_total = max(0, int(total) - int(enriched_total) - int(remaining))

    return {
        "enriched": enriched,
        "unmatched": unmatched,
        "metadata_total": int(total),
        "metadata_enriched_total": int(enriched_total),
        "metadata_remaining": int(remaining),
        "metadata_unmatched_total": int(unmatched_total),
        "warning": warning,
    }


@router.get("/movies/{movie_id}")
async def detail(
    movie_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Negative ids are ephemeral TMDB search results. They are deliberately not
    # written into SQLite just because someone opened a page.
    if movie_id < 0:
        tmdb_id = -movie_id
        tmdb = TMDBService(db)
        if not tmdb.enabled:
            raise HTTPException(404, "Movie not found")
        try:
            details = await tmdb.movie_details(tmdb_id)
        except TMDBUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        movie = _transient_from_tmdb(details)
        ranked = rank_movies(get_interactions(db, user.id), [movie], get_weights(db, user.id))[0]
        base = movie_dict(movie)
        return {
            **_tmdb_overlay(base, details),
            "match_score": ranked["match_score"],
            "predicted_rating": ranked["predicted_rating"],
            "confidence": ranked["confidence"],
            "category": ranked["category"],
            "explanation": ranked["explanation"],
            "components": ranked["components"],
        }

    movie = db.get(Movie, movie_id)
    if not movie:
        raise HTTPException(404, "Movie not found")

    interaction = db.scalar(
        select(UserMovieInteraction).where(
            UserMovieInteraction.user_id == user.id,
            UserMovieInteraction.movie_id == movie_id,
        )
    )
    ranked = rank_movies(get_interactions(db, user.id), [movie], get_weights(db, user.id))[0]
    payload = {
        **movie_dict(movie, interaction),
        "match_score": ranked["match_score"],
        "predicted_rating": ranked["predicted_rating"],
        "confidence": ranked["confidence"],
        "category": ranked["category"],
        "explanation": ranked["explanation"],
        "components": ranked["components"],
    }

    if movie.tmdb_id:
        tmdb = TMDBService(db)
        if tmdb.enabled:
            try:
                payload = _tmdb_overlay(payload, await tmdb.movie_details(int(movie.tmdb_id)))
            except TMDBUnavailable:
                pass
    return payload


@router.get("/movies/{movie_id}/poster")
async def poster(
    movie_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if movie_id < 0:
        tmdb_id = -movie_id
        local_poster = None
        local_backdrop = None
    else:
        movie = db.get(Movie, movie_id)
        if not movie:
            raise HTTPException(404, "Movie not found")
        tmdb_id = movie.tmdb_id
        local_poster = f"{IMG}w500{movie.poster_path}" if movie.poster_path else None
        local_backdrop = f"{IMG}w1280{movie.backdrop_path}" if movie.backdrop_path else None
        if local_poster:
            return {"poster_url": local_poster, "backdrop_url": local_backdrop}
    if not tmdb_id:
        return {"poster_url": None, "backdrop_url": None}
    tmdb = TMDBService(db)
    if not tmdb.enabled:
        return {"poster_url": local_poster, "backdrop_url": local_backdrop}
    try:
        data = await tmdb.movie_summary(int(tmdb_id))
    except TMDBUnavailable:
        return {"poster_url": local_poster, "backdrop_url": local_backdrop}
    return {
        "poster_url": f"{IMG}w500{data.get('poster_path')}" if data.get("poster_path") else local_poster,
        "backdrop_url": f"{IMG}w1280{data.get('backdrop_path')}" if data.get("backdrop_path") else local_backdrop,
    }


@router.get("/movies/{movie_id}/reviews")
async def reviews(
    movie_id: int,
    limit: int = Query(6, ge=1, le=12),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if movie_id < 0:
        tmdb_id = -movie_id
    else:
        movie = db.get(Movie, movie_id)
        if not movie:
            raise HTTPException(404, "Movie not found")
        tmdb_id = movie.tmdb_id
    if not tmdb_id:
        return {"reviews": [], "source": "tmdb", "available": False}
    tmdb = TMDBService(db)
    if not tmdb.enabled:
        return {"reviews": [], "source": "tmdb", "available": False}
    try:
        rows = await tmdb.reviews(int(tmdb_id), limit=limit)
    except TMDBUnavailable:
        return {"reviews": [], "source": "tmdb", "available": False}
    return {"reviews": rows, "source": "tmdb", "available": True}


def _similar_pool(db: Session, movie: Movie, genre_names: list[str], limit: int = 500):
    query = select(Movie).where(
        Movie.id != movie.id,
        or_(Movie.catalog_source.is_not(None), Movie.metadata_updated_at.is_not(None)),
    )
    if genre_names:
        query = query.join(Movie.genres).where(Genre.name.in_(genre_names)).distinct()
    count_expr = func.coalesce(Movie.catalog_rating_count, Movie.vote_count, 0)
    rating_expr = func.coalesce(Movie.catalog_rating * 2.0, Movie.vote_average, 0.0)
    return list(db.scalars(query.order_by(rating_expr.desc(), count_expr.desc()).limit(limit)).unique().all())


@router.get("/movies/{movie_id}/similar")
async def similar(
    movie_id: int,
    limit: int = Query(12, ge=1, le=30),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if movie_id < 0:
        tmdb = TMDBService(db)
        if not tmdb.enabled:
            return {"movies": []}
        try:
            details = await tmdb.movie_details(-movie_id)
        except TMDBUnavailable:
            return {"movies": []}
        movie = _transient_from_tmdb(details)
    else:
        movie = db.get(Movie, movie_id)
        if not movie:
            raise HTTPException(404, "Movie not found")
    genre_names = [g.name for g in movie.genres]
    pool = _similar_pool(db, movie, genre_names)
    base_similarity = SemanticSimilarity().similarities([movie], pool)
    user_rank = {
        row["movie"].id: row
        for row in rank_movies(get_interactions(db, user.id), pool, get_weights(db, user.id))
    }
    rows = []
    for candidate, semantic in zip(pool, base_similarity):
        personalized = user_rank.get(candidate.id)
        match = (personalized["match_score"] / 100) if personalized else 0.5
        score = 0.72 * semantic + 0.28 * match
        rows.append((candidate, score, personalized))
    rows.sort(key=lambda x: x[1], reverse=True)
    return {
        "movies": [
            {
                **movie_dict(candidate),
                "similarity": round(score * 100, 1),
                "match_score": personalized["match_score"] if personalized else None,
                "predicted_rating": personalized["predicted_rating"] if personalized else None,
                "confidence": personalized["confidence"] if personalized else None,
            }
            for candidate, score, personalized in rows[:limit]
        ]
    }


@router.get("/search")
async def search(
    q: str = Query(min_length=2, max_length=120),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Search the 87k local catalogue first; use TMDB only as a gap-filler."""
    norm = normalize_title(q)
    count_expr = func.coalesce(Movie.catalog_rating_count, Movie.vote_count, 0)
    local = list(
        db.scalars(
            select(Movie)
            .where(Movie.normalized_title.contains(norm))
            .order_by((Movie.normalized_title == norm).desc(), count_expr.desc())
            .limit(24)
        ).unique().all()
    )

    interactions = get_interactions(db, user.id)
    interaction_map = {x.movie_id: x for x in interactions}
    candidates: list[Movie] = list(local)
    source = "local-catalogue"
    warning = None

    # The local catalogue covers tens of thousands of films. Only ask TMDB when
    # local title search is sparse, and keep those results ephemeral/read-only.
    if len(local) < 8:
        tmdb = TMDBService(db)
        if tmdb.enabled:
            try:
                raw = await tmdb.search(q)
                known_tmdb = {movie.tmdb_id for movie in local if movie.tmdb_id}
                for item in raw[:12]:
                    tmdb_id = item.get("id")
                    if not tmdb_id or int(tmdb_id) in known_tmdb:
                        continue
                    candidates.append(_transient_from_tmdb(item))
                source = "local+tmdb"
            except TMDBUnavailable:
                warning = "TMDB is unavailable; showing local catalogue results only."

    ranked = rank_movies(interactions, candidates, get_weights(db, user.id))
    return {
        "source": source,
        "results": [
            {
                **movie_dict(row["movie"], interaction_map.get(row["movie"].id)),
                "match_score": row["match_score"],
                "predicted_rating": row["predicted_rating"],
                "confidence": row["confidence"],
                "category": row["category"],
                "explanation": row["explanation"],
            }
            for row in ranked[:24]
        ],
        "warning": warning,
    }
