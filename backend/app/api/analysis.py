from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
import math

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_interactions, get_weights, require_csrf
from app.config import settings as env_settings
from app.database import get_db
from app.importers.letterboxd import parse_letterboxd_files
from app.models.entities import (
    Movie,
    AuthSession,
    DiaryEntry,
    ImportSession,
    ModelEvaluation,
    Recommendation,
    User,
    UserMovieInteraction,
    UserRating,
    UserSetting,
    WatchlistEntry,
)
from app.recommendation.evaluator import evaluate
from app.recommendation.hybrid_ranker import rank_movies
from app.schemas.requests import SettingsUpdate
from app.services.taste import build_taste_profile
from app.utils.text import normalize_title

router = APIRouter(tags=["analysis", "settings"])


@router.get("/evaluation")
def evaluation(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # GET endpoints must be read-only. Persisting evaluation rows here caused
    # SQLite writer-lock failures when users navigated around the app quickly.
    return evaluate(get_interactions(db, user.id))


@router.get("/directors")
def directors(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    interactions = get_interactions(db, user.id)
    by = defaultdict(list)
    all_ratings = [x.rating for x in interactions if x.rating is not None]
    global_mean = mean(all_ratings) if all_ratings else 3
    for interaction in interactions:
        if interaction.rating is None:
            continue
        for director in interaction.movie.director_names:
            by[director].append(interaction.rating)
    rows = []
    for name, ratings in by.items():
        shrunk = (sum(ratings) + global_mean * 2) / (len(ratings) + 2)
        rows.append(
            {
                "name": name,
                "compatibility": round(max(0, min(100, (shrunk - .5) / 4.5 * 100))),
                "films_rated": len(ratings),
                "average_rating": round(mean(ratings), 2),
                "confidence": "High" if len(ratings) >= 5 else "Medium" if len(ratings) >= 3 else "Low",
            }
        )
    return {"directors": sorted(rows, key=lambda x: (x["compatibility"], x["films_rated"]), reverse=True)[:50]}


@router.get("/actors")
def actors(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    interactions = get_interactions(db, user.id)
    by = defaultdict(list)
    all_ratings = [x.rating for x in interactions if x.rating is not None]
    global_mean = mean(all_ratings) if all_ratings else 3
    for interaction in interactions:
        if interaction.rating is None:
            continue
        for actor in interaction.movie.actor_names[:8]:
            by[actor].append(interaction.rating)
    rows = []
    for name, ratings in by.items():
        shrunk = (sum(ratings) + global_mean * 3) / (len(ratings) + 3)
        rows.append(
            {
                "name": name,
                "compatibility": round(max(0, min(100, (shrunk - .5) / 4.5 * 100))),
                "films_rated": len(ratings),
                "average_rating": round(mean(ratings), 2),
                "confidence": "High" if len(ratings) >= 7 else "Medium" if len(ratings) >= 4 else "Low",
            }
        )
    return {"actors": sorted(rows, key=lambda x: (x["compatibility"], x["films_rated"]), reverse=True)[:50]}


@router.post("/compare-users")
async def compare(
    files: list[UploadFile] = File(...),
    _: AuthSession = Depends(require_csrf),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Friend data is parsed in memory and intentionally never persisted.
    total = 0
    payloads = []
    max_bytes = env_settings.max_upload_mb * 1024 * 1024
    for upload in files:
        raw = await upload.read(max_bytes + 1)
        total += len(raw)
        if total > max_bytes:
            raise HTTPException(413, "Comparison upload is too large")
        payloads.append((upload.filename or "upload.csv", raw))
    try:
        other = parse_letterboxd_files(payloads)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    your_interactions = get_interactions(db, user.id)
    yours = {item.movie.normalized_title: item for item in your_interactions if item.rating is not None}
    theirs = {normalize_title(record.title): record for record in other.records if record.rating is not None}
    shared = sorted(set(yours) & set(theirs))
    if not shared:
        return {
            "compatibility": None,
            "message": "No commonly-rated titles were found, so compatibility would be too speculative.",
            "shared": 0,
            "confidence": "Low",
        }

    differences = [abs((yours[key].rating or 0) - (theirs[key].rating or 0)) for key in shared]
    overlap_compatibility = max(0.0, 100 * (1 - mean(differences) / 4.5))
    disagreement = sorted(
        shared,
        key=lambda key: abs((yours[key].rating or 0) - (theirs[key].rating or 0)),
        reverse=True,
    )[:10]
    both_love = [key for key in shared if (yours[key].rating or 0) >= 4 and (theirs[key].rating or 0) >= 4]

    # Reuse only global/public movie metadata to estimate broader taste similarity.
    friend_titles = {normalize_title(record.title) for record in other.records if record.rating is not None}
    known_movies = list(db.scalars(select(Movie).where(Movie.normalized_title.in_(friend_titles))).unique().all()) if friend_titles else []
    by_key = {(movie.normalized_title, movie.year): movie for movie in known_movies}
    by_title = {movie.normalized_title: movie for movie in known_movies}
    friend_known = []
    friend_genre_ratings = defaultdict(list)
    for record in other.records:
        if record.rating is None:
            continue
        movie = by_key.get((normalize_title(record.title), record.year)) or by_title.get(normalize_title(record.title))
        if not movie:
            continue
        friend_known.append((record, movie))
        for genre in movie.genres:
            friend_genre_ratings[genre.name].append(float(record.rating))

    your_genres = build_taste_profile(your_interactions).get("genre_scores", {})
    friend_genres = {
        genre: max(-1.0, min(1.0, (mean(ratings) - 2.75) / 2.25))
        for genre, ratings in friend_genre_ratings.items()
    }
    genre_keys = set(your_genres) | set(friend_genres)
    metadata_compatibility = None
    if genre_keys and friend_known:
        left = [float(your_genres.get(key, 0)) for key in genre_keys]
        right = [float(friend_genres.get(key, 0)) for key in genre_keys]
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm and right_norm:
            cosine = sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
            metadata_compatibility = max(0.0, min(100.0, (cosine + 1) * 50))

    compatibility = overlap_compatibility
    if metadata_compatibility is not None and len(friend_known) >= 5:
        compatibility = .75 * overlap_compatibility + .25 * metadata_compatibility

    shared_genres = Counter()
    for key in shared:
        if (yours[key].rating or 0) >= 3.5 and (theirs[key].rating or 0) >= 3.5:
            for genre in yours[key].movie.genres:
                shared_genres[genre.name] += 1

    # Rank films the friend loves but the current user has not rated using the
    # current user's own MyBoxd model. This makes "watch together" actionable.
    your_rated_ids = {item.movie_id for item in your_interactions if item.rating is not None}
    friend_loved_candidates = []
    friend_rating_by_movie = {}
    for record, movie in friend_known:
        if (record.rating or 0) >= 4.0 and movie.id not in your_rated_ids:
            friend_loved_candidates.append(movie)
            friend_rating_by_movie[movie.id] = float(record.rating or 0)
    personalized = rank_movies(your_interactions, friend_loved_candidates, get_weights(db, user.id))
    together = []
    for row in personalized[:15]:
        friend_rating = friend_rating_by_movie.get(row["movie"].id, 0)
        combined = .55 * row["match_score"] + .45 * (friend_rating / 5 * 100)
        together.append(
            {
                "title": row["movie"].title,
                "score": round(combined, 1),
                "your_match": row["match_score"],
                "your_predicted_rating": row["predicted_rating"],
                "friend_rating": friend_rating,
                "reason": "Your friend rated it highly and MyBoxd also sees a strong fit for you.",
            }
        )
    together.sort(key=lambda row: row["score"], reverse=True)

    friend_unseen = [
        record for record in other.records
        if (record.rating or 0) >= 4.5 and normalize_title(record.title) not in yours
    ]
    confidence = "High" if len(shared) >= 30 else "Medium" if len(shared) >= 10 else "Low"
    return {
        "compatibility": round(compatibility),
        "overlap_compatibility": round(overlap_compatibility),
        "metadata_compatibility": round(metadata_compatibility) if metadata_compatibility is not None else None,
        "friend_metadata_matches": len(friend_known),
        "confidence": confidence,
        "shared": len(shared),
        "movies_both_love": [yours[key].movie.title for key in both_love[:10]],
        "biggest_disagreements": [
            {"title": yours[key].movie.title, "you": yours[key].rating, "friend": theirs[key].rating}
            for key in disagreement
        ],
        "favorite_shared_genres": [
            {"genre": genre, "shared_liked_films": count}
            for genre, count in shared_genres.most_common(8)
        ],
        "your_loves_they_havent_rated": [
            item.movie.title
            for item in yours.values()
            if (item.rating or 0) >= 4.5 and item.movie.normalized_title not in theirs
        ][:10],
        "their_loves_you_havent_rated": [record.title for record in friend_unseen[:10]],
        "best_to_watch_together": together[:10],
    }


@router.get("/settings")
def settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total = db.scalar(
        select(func.count(func.distinct(Movie.id)))
        .select_from(Movie)
        .join(UserMovieInteraction)
        .where(UserMovieInteraction.user_id == user.id)
    ) or 0
    enriched = db.scalar(
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
    return {
        "tmdb_configured": bool(env_settings.tmdb_api_key),
        "weights": get_weights(db, user.id),
        "database": "postgresql" if env_settings.database_url.startswith("postgresql") else "sqlite",
        "environment": env_settings.environment,
        "privacy": "Your Letterboxd records and recommendation settings are scoped to your account.",
        "metadata_total": int(total),
        "metadata_enriched": int(enriched),
        "metadata_remaining": int(remaining),
        "metadata_unmatched": max(0, int(total) - int(enriched) - int(remaining)),
    }


@router.put("/settings")
def update(
    req: SettingsUpdate,
    _: AuthSession = Depends(require_csrf),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.scalar(select(UserSetting).where(UserSetting.user_id == user.id, UserSetting.key == "recommendation_weights"))
    if not row:
        row = UserSetting(user_id=user.id, key="recommendation_weights", value=req.weights.model_dump())
        db.add(row)
    else:
        row.value = req.weights.model_dump()
    db.commit()
    return {"weights": row.value}


@router.delete("/settings/data")
def clear_user_data(
    _: AuthSession = Depends(require_csrf),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Global Movie/TMDB metadata remains reusable; only private user-owned rows are removed.
    for model in (Recommendation, ModelEvaluation, DiaryEntry, WatchlistEntry, UserRating, UserMovieInteraction, ImportSession, UserSetting):
        db.execute(delete(model).where(model.user_id == user.id))
    db.commit()
    return {"cleared": True}


@router.delete("/settings/account")
def delete_account(
    response: Response,
    _: AuthSession = Depends(require_csrf),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.delete(user)
    db.commit()
    response.delete_cookie(env_settings.cookie_name, path="/", secure=env_settings.cookie_secure, samesite=env_settings.cookie_samesite)
    return {"deleted": True}
