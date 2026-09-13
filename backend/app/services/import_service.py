from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importers.letterboxd import ImportResult
from app.models.entities import DiaryEntry, ImportSession, Movie, User, UserMovieInteraction, UserRating, WatchlistEntry
from app.utils.text import normalize_title


def persist_import(db: Session, user: User, result: ImportResult):
    created = 0
    for rec in result.records:
        norm = normalize_title(rec.title)
        movie = db.scalar(select(Movie).where(Movie.normalized_title == norm, Movie.year == rec.year))
        if not movie:
            movie = Movie(title=rec.title, normalized_title=norm, year=rec.year)
            db.add(movie)
            db.flush()
            created += 1
        interaction = db.scalar(
            select(UserMovieInteraction).where(
                UserMovieInteraction.user_id == user.id,
                UserMovieInteraction.movie_id == movie.id,
            )
        )
        if not interaction:
            interaction = UserMovieInteraction(user_id=user.id, movie_id=movie.id)
            db.add(interaction)
        if rec.rating is not None:
            interaction.rating = rec.rating
        interaction.watched = bool(interaction.watched) or rec.watched
        interaction.watchlist = bool(interaction.watchlist) or rec.watchlist
        interaction.rewatch_count = max(interaction.rewatch_count or 0, rec.rewatch_count)
        interaction.last_watched = rec.last_watched or interaction.last_watched
        interaction.review = rec.review or interaction.review
        interaction.letterboxd_uri = rec.letterboxd_uri or interaction.letterboxd_uri
        if rec.rating is not None:
            rating = db.scalar(select(UserRating).where(UserRating.user_id == user.id, UserRating.movie_id == movie.id))
            if rating:
                rating.rating = rec.rating
                rating.rated_at = rec.last_watched
            else:
                db.add(UserRating(user_id=user.id, movie_id=movie.id, rating=rec.rating, rated_at=rec.last_watched))
        if rec.watchlist and not db.scalar(
            select(WatchlistEntry).where(WatchlistEntry.user_id == user.id, WatchlistEntry.movie_id == movie.id)
        ):
            db.add(WatchlistEntry(user_id=user.id, movie_id=movie.id))
        for watched_date in rec.diary_dates:
            if not db.scalar(
                select(DiaryEntry).where(
                    DiaryEntry.user_id == user.id,
                    DiaryEntry.movie_id == movie.id,
                    DiaryEntry.watched_date == watched_date,
                )
            ):
                db.add(
                    DiaryEntry(
                        user_id=user.id,
                        movie_id=movie.id,
                        watched_date=watched_date,
                        rating=rec.rating,
                        rewatch=rec.rewatch_count > 0,
                    )
                )
    session = ImportSession(
        user_id=user.id,
        source_files=result.source_files,
        rows_processed=result.rows_processed,
        movies_created=created,
        errors=result.errors,
    )
    db.add(session)
    db.commit()
    return {
        "import_session_id": session.id,
        "movies": len(result.records),
        "movies_created": created,
        "rows_processed": result.rows_processed,
        "source_files": result.source_files,
        "errors": result.errors,
    }
