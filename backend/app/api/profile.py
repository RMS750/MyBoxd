from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_interactions
from app.database import get_db
from app.models.entities import DiaryEntry, User
from app.services.taste import build_stats, build_taste_dna, build_taste_profile

router = APIRouter(tags=["profile"])


@router.get("/profile")
def profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_taste_profile(get_interactions(db, user.id))


@router.get("/profile/taste-dna")
def taste_dna(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    interactions = get_interactions(db, user.id)
    return build_taste_dna(interactions, build_taste_profile(interactions))


@router.get("/stats")
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_stats(get_interactions(db, user.id))


@router.get("/timeline")
def timeline(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    interactions = {x.movie_id: x for x in get_interactions(db, user.id)}
    diary = list(
        db.scalars(
            select(DiaryEntry)
            .where(DiaryEntry.user_id == user.id)
            .order_by(DiaryEntry.watched_date)
        ).all()
    )
    group = defaultdict(list)
    for entry in diary:
        group[entry.watched_date.year].append(entry)
    points = []
    for year, entries in sorted(group.items()):
        ratings = [e.rating for e in entries if e.rating is not None]
        genres = defaultdict(int)
        runtimes: list[int] = []
        popularities: list[float] = []
        for entry in entries:
            interaction = interactions.get(entry.movie_id)
            if not interaction:
                continue
            for genre in interaction.movie.genres:
                genres[genre.name] += 1
            if interaction.movie.runtime:
                runtimes.append(interaction.movie.runtime)
            if interaction.movie.popularity is not None:
                popularities.append(interaction.movie.popularity)
        points.append(
            {
                "year": year,
                "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
                "favorite_genre": max(genres, key=genres.get) if genres else None,
                "average_runtime": round(sum(runtimes) / len(runtimes), 1) if runtimes else None,
                "average_popularity": round(sum(popularities) / len(popularities), 1) if popularities else None,
                "watches": len(entries),
            }
        )
    return {"available": bool(points), "points": points}
