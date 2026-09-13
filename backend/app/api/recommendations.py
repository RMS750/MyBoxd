from __future__ import annotations

import random
import time
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_interactions, get_weights, require_csrf
from app.database import get_db
from app.models.entities import AuthSession, Genre, Movie, User
from app.recommendation.context_scoring import context_adjustment
from app.recommendation.hybrid_ranker import rank_movies
from app.recommendation.intent_parser import parse_intent
from app.schemas.requests import ContextRecommendationRequest, RouletteRequest
from app.services.serialize import movie_dict
from app.services.taste import build_taste_profile

router = APIRouter(tags=["recommendations"])
_RANK_CACHE: dict[tuple, tuple[float, tuple[list, list[Movie], dict]]] = {}
_FEED_CACHE: dict[tuple, tuple[float, dict]] = {}
_RANK_TTL_SECONDS = 180.0
_FEED_TTL_SECONDS = 180.0
_RANK_LOCK = threading.Lock()


def _ser(row, interaction=None):
    return {
        **movie_dict(row["movie"], interaction),
        "match_score": row["match_score"],
        "predicted_rating": row["predicted_rating"],
        "confidence": row["confidence"],
        "category": row["category"],
        "components": row["components"],
        "explanation": row["explanation"],
    }


def _effective_popularity(movie: Movie) -> float:
    value = movie.popularity if movie.popularity is not None else movie.catalog_popularity
    return float(value if value is not None else 50.0)


def _effective_count(movie: Movie) -> int:
    value = movie.catalog_rating_count if movie.catalog_rating_count is not None else movie.vote_count
    return int(value or 0)


def _effective_public_rating(movie: Movie) -> float | None:
    if movie.letterboxd_rating is not None:
        return float(movie.letterboxd_rating)
    if movie.catalog_rating is not None:
        return float(movie.catalog_rating)
    if movie.vote_average is not None:
        return float(movie.vote_average) / 2.0
    return None


def _blocked_ids(interactions) -> set[int]:
    return {item.movie_id for item in interactions if item.watched or item.watchlist}


def _base_query(blocked: set[int]):
    query = select(Movie).where(
        (Movie.catalog_source.is_not(None)) | (Movie.metadata_updated_at.is_not(None))
    )
    if blocked:
        query = query.where(~Movie.id.in_(blocked))
    return query


def _extend_unique(out: list[Movie], seen: set[int], movies, limit: int):
    for movie in movies:
        if movie.id in seen:
            continue
        seen.add(movie.id)
        out.append(movie)
        if len(out) >= limit:
            break


def _candidate_pool(db: Session, interactions, max_pool: int = 1200) -> list[Movie]:
    """Build a broad, local-only candidate pool.

    Earlier builds fetched and persisted TMDB discovery rows while GET requests were open.
    That made five simultaneous Discover requests fight over SQLite's single writer
    lock. MyBoxd never writes or calls TMDB on the recommendation critical path.
    """
    blocked = _blocked_ids(interactions)
    profile = build_taste_profile(interactions)
    positive_genres = [
        name for name, score in profile.get("genre_scores", {}).items() if score > 0.04
    ][:5]

    rating_expr = func.coalesce(Movie.catalog_rating * 2.0, Movie.vote_average, 0.0)
    count_expr = func.coalesce(Movie.catalog_rating_count, Movie.vote_count, 0)
    popularity_expr = func.coalesce(Movie.catalog_popularity, Movie.popularity, 50.0)

    out: list[Movie] = []
    seen: set[int] = set()

    # Personal genre lanes first so the pool is not just globally popular cinema.
    if positive_genres:
        for genre_name in positive_genres:
            query = (
                _base_query(blocked)
                .join(Movie.genres)
                .where(Genre.name == genre_name, count_expr >= 20)
                .order_by(rating_expr.desc(), count_expr.desc())
                .limit(180)
            )
            _extend_unique(out, seen, db.scalars(query).unique().all(), max_pool)
            if len(out) >= max_pool:
                return out

    # High-quality films with enough public evidence.
    quality = (
        _base_query(blocked)
        .where(count_expr >= 35)
        .order_by(rating_expr.desc(), count_expr.desc())
        .limit(420)
    )
    _extend_unique(out, seen, db.scalars(quality).unique().all(), max_pool)

    # Popular/mainstream lane.
    popular = _base_query(blocked).order_by(count_expr.desc(), rating_expr.desc()).limit(260)
    _extend_unique(out, seen, db.scalars(popular).unique().all(), max_pool)

    # Obscure-but-established lane for genuine hidden gems.
    obscure = (
        _base_query(blocked)
        .where(popularity_expr <= 55, count_expr >= 18)
        .order_by(rating_expr.desc(), count_expr.desc())
        .limit(360)
    )
    _extend_unique(out, seen, db.scalars(obscure).unique().all(), max_pool)

    # Recent lane prevents an older benchmark catalogue from dominating everything.
    recent = (
        _base_query(blocked)
        .where(Movie.year >= 2010, count_expr >= 10)
        .order_by(rating_expr.desc(), count_expr.desc())
        .limit(260)
    )
    _extend_unique(out, seen, db.scalars(recent).unique().all(), max_pool)

    if len(out) < min(500, max_pool):
        fallback = _base_query(blocked).order_by(count_expr.desc(), rating_expr.desc()).limit(max_pool)
        _extend_unique(out, seen, db.scalars(fallback).unique().all(), max_pool)

    return out[:max_pool]


async def _candidates(db: Session, interactions):
    # Kept async for API compatibility with contextual/roulette routes.
    return _candidate_pool(db, interactions)


def _cache_key(user_id: int, interactions, weights: dict) -> tuple:
    interaction_sig = tuple(
        sorted(
            (
                int(item.movie_id),
                None if item.rating is None else float(item.rating),
                bool(item.watched),
                bool(item.watchlist),
                int(item.rewatch_count or 0),
                str(item.updated_at or ""),
            )
            for item in interactions
        )
    )
    weight_sig = tuple(sorted((key, round(float(value), 6)) for key, value in weights.items()))
    return user_id, interaction_sig, weight_sig


def _hate_reason(row, baseline: float) -> str:
    movie = row["movie"]
    reasons: list[str] = []
    public = _effective_public_rating(movie)
    if public is not None and public < 2.6:
        source = "Letterboxd" if movie.letterboxd_rating is not None else "MovieLens" if movie.catalog_rating is not None else "TMDB"
        reasons.append(f"{source} viewers rate it only {public:.2f}/5")
    if float(row["predicted_rating"]) <= baseline - 0.45:
        reasons.append(f"MyBoxd predicts just {float(row['predicted_rating']):.1f}/5 for you")
    if float(row.get("semantic_negative", 0.0)) >= 0.50:
        reasons.append("it resembles films you rated near the bottom of your history")
    weakest = sorted(row.get("components", {}).items(), key=lambda item: item[1])
    labels = {
        "genre": "the genre mix clashes with your ratings",
        "semantic": "the themes look closer to your misses than your favorites",
        "creator": "the director/cast signal is weak for you",
        "community": "public reception is a warning sign",
        "predicted_rating": "your personal rating model is unconvinced",
    }
    for key, value in weakest:
        if value < 0.38 and key in labels and labels[key] not in reasons:
            reasons.append(labels[key])
        if len(reasons) >= 3:
            break
    if not reasons:
        reasons.append("too many of your personal taste signals point the wrong way")
    text = "; ".join(reasons[:3])
    return text[0].upper() + text[1:] + "."


def _hate_category(score: float) -> str:
    if score <= 25:
        return "AVOID AT ALL COSTS"
    if score <= 40:
        return "PROBABLY PAINFUL"
    return "NOT FOR YOU"


def _take(rows, seen: set[int], limit: int, predicate=None):
    out = []
    for row in rows:
        if row["movie"].id in seen:
            continue
        if predicate and not predicate(row):
            continue
        seen.add(row["movie"].id)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _partition(ranked, profile, *, top_limit=24, safe_limit=18, gem_limit=18, wild_limit=18, anti_limit=18):
    """Create non-overlapping rails from one ranking pass.

    Top Matches are reserved first, so a score-80 title can no longer disappear
    from Top Matches merely because another rail claimed it before the top rail.
    """
    seen: set[int] = set()
    top = _take(ranked, seen, top_limit)

    safe = _take(
        ranked,
        seen,
        safe_limit,
        lambda row: row["category"] == "SAFE BET" or (
            float(row["match_score"]) >= 72 and row["confidence"] != "Low"
        ),
    )

    def strict_gem(row):
        movie = row["movie"]
        return (
            float(row["match_score"]) >= 67
            and _effective_popularity(movie) <= 45
            and _effective_count(movie) >= 18
        )

    gem_candidates = [row for row in ranked if row["movie"].id not in seen and strict_gem(row)]
    gem_candidates.sort(
        key=lambda row: (
            float(row["match_score"]) + 0.22 * (45.0 - min(45.0, _effective_popularity(row["movie"]))),
            _effective_count(row["movie"]),
        ),
        reverse=True,
    )
    gems = _take(gem_candidates, seen, gem_limit)
    if len(gems) < gem_limit:
        relaxed = [
            row for row in ranked
            if row["movie"].id not in seen
            and float(row["match_score"]) >= 60
            and _effective_popularity(row["movie"]) <= 60
            and _effective_count(row["movie"]) >= 10
        ]
        relaxed.sort(
            key=lambda row: float(row["match_score"]) + 0.12 * (60 - min(60.0, _effective_popularity(row["movie"]))),
            reverse=True,
        )
        gems.extend(_take(relaxed, seen, gem_limit - len(gems)))

    wild = _take(
        ranked,
        seen,
        wild_limit,
        lambda row: (
            row["category"] == "WILD CARD"
            or float(row.get("components", {}).get("novelty", 0.0)) >= 0.60
        )
        and float(row["match_score"]) >= 52,
    )

    baseline = float(profile.get("average_rating") or 3.0)
    spread = max(0.55, float(profile.get("rating_std") or 0.75))
    anti_threshold = baseline - max(0.20, 0.30 * spread)
    anti_pool = [
        row for row in reversed(ranked)
        if row["movie"].id not in seen
        and (
            float(row["match_score"]) <= 48
            or float(row["predicted_rating"]) <= anti_threshold
            or ((_effective_public_rating(row["movie"]) or 5.0) < 2.65)
        )
    ]
    anti_pool.sort(
        key=lambda row: (
            float(row["match_score"]),
            _effective_public_rating(row["movie"]) if _effective_public_rating(row["movie"]) is not None else 5.0,
            float(row["predicted_rating"]),
        )
    )
    anti = _take(anti_pool, seen, anti_limit)

    return {"top": top, "safe": safe, "gems": gems, "wild": wild, "anti": anti}


def _ranked_snapshot(db: Session, user: User, interactions, weights: dict):
    """Rank the local catalogue once and reuse it across app pages.

    Discover, Dashboard, Search browse, Hidden Gems and Hate used to launch
    separate ranking jobs. With a large catalogue that made navigation feel
    progressively slower. This cache is invalidated automatically whenever
    the user's interactions or tuning weights change.
    """
    key = _cache_key(user.id, interactions, weights)
    cached = _RANK_CACHE.get(key)
    if cached and time.monotonic() - cached[0] <= _RANK_TTL_SECONDS:
        return key, cached[1]

    # React pages can request the same feed at nearly the same moment. Only one
    # request should pay the first ranking cost; the rest wait briefly and reuse
    # the completed snapshot instead of duplicating CPU work.
    with _RANK_LOCK:
        cached = _RANK_CACHE.get(key)
        if cached and time.monotonic() - cached[0] <= _RANK_TTL_SECONDS:
            return key, cached[1]
        candidates = _candidate_pool(db, interactions, max_pool=900)
        ranked = rank_movies(interactions, candidates, weights)
        profile = build_taste_profile(interactions)
        snapshot = (ranked, candidates, profile)
        _RANK_CACHE.clear()
        _RANK_CACHE[key] = (time.monotonic(), snapshot)
        return key, snapshot


def _build_feed(db: Session, user: User, interactions, weights: dict) -> dict:
    key = _cache_key(user.id, interactions, weights)
    cached = _FEED_CACHE.get(key)
    if cached and time.monotonic() - cached[0] <= _FEED_TTL_SECONDS:
        return cached[1]

    key, (ranked, candidates, profile) = _ranked_snapshot(db, user, interactions, weights)
    sections = _partition(ranked, profile)

    baseline = float(profile.get("average_rating") or 3.0)
    anti_serialized = []
    for row in sections["anti"]:
        item = _ser(row)
        reason = _hate_reason(row, baseline)
        item["hate_reason"] = reason
        item["explanation"] = reason
        item["category"] = _hate_category(float(row["match_score"]))
        anti_serialized.append(item)

    payload = {
        "top": [_ser(row) for row in sections["top"]],
        "safe": [_ser(row) for row in sections["safe"]],
        "gems": [_ser(row) for row in sections["gems"]],
        "wild": [_ser(row) for row in sections["wild"]],
        "anti": anti_serialized,
        "candidate_count": len(candidates),
        "catalogue_backed": any(movie.catalog_source for movie in candidates),
    }
    # Keep only a few recent user snapshots.
    _FEED_CACHE.clear()
    _FEED_CACHE[key] = (time.monotonic(), payload)
    return payload


@router.get("/discover-feed")
def discover_feed(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interactions = get_interactions(db, user.id)
    return _build_feed(db, user, interactions, get_weights(db, user.id))


@router.get("/recommendations")
async def recommendations(
    limit: int = Query(20, ge=1, le=100),
    category: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interactions = get_interactions(db, user.id)
    weights = get_weights(db, user.id)
    _, (ranked, _, _) = _ranked_snapshot(db, user, interactions, weights)
    if category:
        ranked = [row for row in ranked if row["category"].casefold() == category.casefold()]
    # Top recommendations are intentionally score-first. Do not let diversity
    # penalties push 60-point movies above genuine 80-point matches.
    return {"recommendations": [_ser(row) for row in ranked[:limit]]}


@router.post("/recommendations/context")
async def contextual(
    req: ContextRecommendationRequest,
    _: AuthSession = Depends(require_csrf),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interactions = get_interactions(db, user.id)
    candidates = await _candidates(db, interactions)
    parsed = parse_intent(" ".join(value for value in [req.prompt, req.mood or ""] if value))
    max_values = [value for value in (req.max_runtime, parsed.get("max_runtime")) if value]
    max_runtime = min(max_values) if max_values else None
    min_values = [value for value in (req.min_runtime, parsed.get("min_runtime")) if value]
    min_runtime = max(min_values) if min_values else None
    genres = {genre.casefold() for genre in req.genres + parsed.get("genres", [])}
    avoid = {value.casefold() for value in req.avoid + parsed.get("avoid", [])}
    keywords = {value.casefold() for value in parsed.get("keywords", [])}
    filtered = []
    for movie in candidates:
        if max_runtime and movie.runtime and movie.runtime > max_runtime:
            continue
        if min_runtime and movie.runtime and movie.runtime < min_runtime:
            continue
        effective_decade = req.decade or parsed.get("decade")
        if effective_decade and movie.year and (movie.year // 10) * 10 != effective_decade:
            continue
        effective_language = req.language or parsed.get("language")
        if effective_language and movie.original_language and movie.original_language.casefold() != str(effective_language).casefold():
            continue
        if req.country and not any(req.country.casefold() in country.casefold() for country in movie.production_countries or []):
            continue
        if genres and not genres.intersection({genre.name.casefold() for genre in movie.genres}):
            continue
        popularity = _effective_popularity(movie)
        if parsed.get("popularity_max") is not None and popularity > parsed["popularity_max"]:
            continue
        if parsed.get("popularity_min") is not None and popularity < parsed["popularity_min"]:
            continue
        haystack = " ".join([
            movie.overview or "",
            " ".join(movie.keywords or []),
            " ".join(genre.name for genre in movie.genres),
        ]).casefold()
        if any(value in haystack for value in avoid):
            continue
        filtered.append(movie)

    ranked = rank_movies(interactions, filtered or candidates, get_weights(db, user.id))
    targets = {
        "darkness": req.darkness if req.darkness is not None else parsed.get("darkness"),
        "pace": req.pace if req.pace is not None else parsed.get("pace"),
        "experimental": req.experimental if req.experimental is not None else (80 if parsed.get("prefer_experimental") is True else 20 if parsed.get("prefer_experimental") is False else None),
        "mainstream": req.mainstream,
        "emotional_intensity": req.emotional_intensity if req.emotional_intensity is not None else parsed.get("emotional_intensity"),
    }
    for row in ranked:
        haystack = " ".join([row["movie"].overview or "", " ".join(row["movie"].keywords or [])]).casefold()
        keyword_bonus = min(8, 2 * sum(keyword in haystack for keyword in keywords)) if keywords else 0
        row["match_score"] = round(
            max(0, min(100, row["match_score"] + keyword_bonus + context_adjustment(row["movie"], targets, req.company or parsed.get("company")))),
            1,
        )
    ranked.sort(key=lambda row: row["match_score"], reverse=True)
    return {"interpreted": parsed, "recommendations": [_ser(row) for row in ranked[: req.limit]]}


@router.get("/watchlist/ranked")
def watchlist(
    sort: str = "best",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interactions = get_interactions(db, user.id)
    watchlist_items = [item for item in interactions if item.watchlist and not item.watched]
    ranked = rank_movies(interactions, [item.movie for item in watchlist_items], get_weights(db, user.id))
    interaction_map = {item.movie_id: item for item in watchlist_items}
    keys = {
        "predicted": lambda row: row["predicted_rating"],
        "shortest": lambda row: -(row["movie"].runtime or 9999),
        "longest": lambda row: row["movie"].runtime or 0,
        "popular": lambda row: _effective_popularity(row["movie"]),
        "obscure": lambda row: -_effective_popularity(row["movie"]),
        "newest": lambda row: row["movie"].year or 0,
        "oldest": lambda row: -(row["movie"].year or 9999),
    }
    if sort in keys:
        ranked.sort(key=keys[sort], reverse=True)
    return {"recommendations": [_ser(row, interaction_map.get(row["movie"].id)) for row in ranked]}


@router.get("/hidden-gems")
async def gems(
    popularity_max: float = 45,
    limit: int = Query(20, ge=1, le=80),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interactions = get_interactions(db, user.id)
    weights = get_weights(db, user.id)
    _, (ranked, _, _) = _ranked_snapshot(db, user, interactions, weights)
    # Hidden Gems is deliberately a different job from Recommended: strong
    # personal fit + genuinely lower popularity, excluding the main top shelf.
    general_top_ids = {row["movie"].id for row in ranked[:24]}
    rows = [
        row for row in ranked
        if row["movie"].id not in general_top_ids
        and _effective_popularity(row["movie"]) <= popularity_max
        and _effective_count(row["movie"]) >= 18
        and float(row["match_score"]) >= 64
    ]
    rows.sort(
        key=lambda row: float(row["match_score"]) + 0.18 * (popularity_max - min(popularity_max, _effective_popularity(row["movie"]))),
        reverse=True,
    )
    return {"recommendations": [_ser(row) for row in rows[:limit]]}


@router.get("/anti-recommendations")
async def anti(
    limit: int = Query(24, ge=1, le=80),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interactions = get_interactions(db, user.id)
    weights = get_weights(db, user.id)
    _, (ranked, _, profile) = _ranked_snapshot(db, user, interactions, weights)
    baseline = float(profile.get("average_rating") or 3.0)
    spread = max(0.55, float(profile.get("rating_std") or 0.75))
    threshold = baseline - max(0.20, 0.30 * spread)
    negative = [
        row for row in ranked
        if row["predicted_rating"] <= threshold
        or row["match_score"] <= 48
        or ((_effective_public_rating(row["movie"]) or 5.0) < 2.65)
    ]
    negative.sort(
        key=lambda row: (
            row["match_score"],
            _effective_public_rating(row["movie"]) if _effective_public_rating(row["movie"]) is not None else 5.0,
            row["predicted_rating"],
            -float(row.get("semantic_negative", 0.0)),
        )
    )
    items = []
    for row in negative[:limit]:
        item = _ser(row)
        reason = _hate_reason(row, baseline)
        item["hate_reason"] = reason
        item["explanation"] = reason
        item["category"] = _hate_category(float(row["match_score"]))
        items.append(item)
    return {
        "note": "This is the deliberately mean rail: low personal fit plus negative-history and public-quality evidence.",
        "recommendations": items,
    }


@router.post("/roulette")
async def roulette(
    req: RouletteRequest,
    _: AuthSession = Depends(require_csrf),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interactions = get_interactions(db, user.id)
    candidates = [item.movie for item in interactions if item.watchlist and not item.watched] if req.watchlist_only else await _candidates(db, interactions)
    if req.max_runtime:
        candidates = [movie for movie in candidates if not movie.runtime or movie.runtime <= req.max_runtime]
    ranked = rank_movies(interactions, candidates, get_weights(db, user.id))
    ranked = [
        row for row in ranked
        if (not req.hidden_gem or _effective_popularity(row["movie"]) <= 45)
        and (not req.category or row["category"].casefold() == req.category.casefold())
    ]
    pool = ranked[:24]
    if not pool:
        raise HTTPException(404, "No movie matches those roulette filters.")
    return _ser(random.choices(pool, weights=[max(1, row["match_score"] - 35) for row in pool], k=1)[0])
