from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_csrf
from app.config import settings
from app.database import get_db
from app.importers.letterboxd import parse_letterboxd_files
from app.models.entities import AuthSession, DiaryEntry, ImportSession, ModelEvaluation, Movie, Recommendation, User, UserMovieInteraction, UserRating, WatchlistEntry
from app.services.import_service import persist_import
from app.services.tmdb import TMDBService, TMDBUnavailable

logger = logging.getLogger("myboxd.import")
router = APIRouter(tags=["import"])
_import_locks: dict[int, asyncio.Lock] = {}


@router.post("/import", summary="Import a Letterboxd export")
async def import_letterboxd(
    files: list[UploadFile] = File(...),
    mode: str = Form("merge"),
    _: AuthSession = Depends(require_csrf),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mode = mode.casefold().strip()
    if mode not in {"merge", "replace"}:
        raise HTTPException(400, "Import mode must be merge or replace")
    if not files or len(files) > 20:
        raise HTTPException(400, "Upload between 1 and 20 Letterboxd files")
    payloads: list[tuple[str, bytes]] = []
    total = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    for upload in files:
        name = upload.filename or "upload.csv"
        if not name.casefold().endswith((".csv", ".zip")):
            raise HTTPException(400, f"Unsupported file type: {name}")
        raw = await upload.read(max_bytes + 1)
        total += len(raw)
        if len(raw) > max_bytes or total > max_bytes:
            raise HTTPException(413, f"Upload is too large. Maximum total size is {settings.max_upload_mb} MB.")
        payloads.append((name, raw))
    try:
        parsed = parse_letterboxd_files(payloads)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    # A Letterboxd import can spend time enriching many movies. Do not allow a
    # second import for the same account to compete for SQLite's single writer.
    import_lock = _import_locks.setdefault(user.id, asyncio.Lock())
    if import_lock.locked():
        raise HTTPException(409, "An import is already in progress for this account. Please wait for it to finish.")
    await import_lock.acquire()
    try:
        return await _finish_import(db, user, parsed, mode)
    finally:
        import_lock.release()


async def _finish_import(db: Session, user: User, parsed, mode: str):
    # Replace is intentionally applied only after the new upload has parsed successfully.
    # Global movie/TMDB metadata stays cached and reusable; only this user's private data is reset.
    if mode == "replace":
        for model in (Recommendation, ModelEvaluation, DiaryEntry, WatchlistEntry, UserRating, UserMovieInteraction, ImportSession):
            db.execute(delete(model).where(model.user_id == user.id))

    summary = persist_import(db, user, parsed)
    tmdb = TMDBService(db)
    enriched = unmatched = 0
    warnings: list[str] = []
    if tmdb.enabled:
        # Enrich the highest-signal history first: rated films before unrated
        # watches/watchlist entries. Taste modeling is only as good as its metadata.
        missing_interactions = list(
            db.scalars(
                select(UserMovieInteraction).where(UserMovieInteraction.user_id == user.id)
            ).unique().all()
        )
        missing_interactions = [
            item for item in missing_interactions
            if item.movie.metadata_updated_at is None and item.movie.match_confidence is None
        ]
        missing_interactions.sort(
            key=lambda item: (
                item.rating is not None,
                float(item.rating or 0),
                bool(item.watched),
                int(item.rewatch_count or 0),
            ),
            reverse=True,
        )
        movies = []
        seen_movie_ids = set()
        for item in missing_interactions:
            if item.movie_id in seen_movie_ids:
                continue
            movies.append(item.movie)
            seen_movie_ids.add(item.movie_id)
            # This is only the initial import batch. The frontend automatically
            # continues /movies/enrich in additional batches until every title has
            # been attempted. A value <= 0 means no initial cap.
            if settings.tmdb_enrich_limit > 0 and len(movies) >= settings.tmdb_enrich_limit:
                break
        for movie in movies:
            try:
                if await tmdb.enrich_movie(movie):
                    enriched += 1
                else:
                    unmatched += 1
                # Release SQLite's write lock between movies instead of holding
                # one transaction across dozens of network requests.
                db.commit()
            except TMDBUnavailable as exc:
                db.rollback()
                warnings.append(str(exc))
                break
        remaining_unattempted = len(list(db.scalars(
            select(Movie.id)
            .join(UserMovieInteraction)
            .where(
                UserMovieInteraction.user_id == user.id,
                Movie.metadata_updated_at.is_(None),
                Movie.match_confidence.is_(None),
            )
        ).all()))
        if remaining_unattempted:
            warnings.append(
                f"{remaining_unattempted} titles are queued for continued TMDB matching. "
                "The MyBoxd frontend will continue automatically in batches."
            )
    else:
        warnings.append("TMDB_API_KEY is missing. Import succeeded, but metadata enrichment was skipped.")

    logger.info(
        "Letterboxd import completed user_id=%s mode=%s records=%s enriched=%s skipped_rows=%s",
        user.id,
        mode,
        summary["movies"],
        enriched,
        len(summary["errors"]),
    )
    # Coverage values let the browser continue enrichment without requiring any
    # terminal commands from normal users.
    total_movies = db.scalar(
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
    remaining_unattempted = db.scalar(
        select(func.count(func.distinct(Movie.id)))
        .select_from(Movie)
        .join(UserMovieInteraction)
        .where(
            UserMovieInteraction.user_id == user.id,
            Movie.metadata_updated_at.is_(None),
            Movie.match_confidence.is_(None),
        )
    ) or 0
    unmatched_total = max(0, int(total_movies) - int(enriched_total) - int(remaining_unattempted))
    return {
        **summary,
        "mode": mode,
        "tmdb_enriched": enriched,
        "tmdb_unmatched": unmatched,
        "metadata_total": int(total_movies),
        "metadata_enriched_total": int(enriched_total),
        "metadata_remaining": int(remaining_unattempted),
        "metadata_unmatched_total": int(unmatched_total),
        "warnings": warnings,
    }
