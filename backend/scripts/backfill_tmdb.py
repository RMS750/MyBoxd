from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models.entities import Movie, UserMovieInteraction
from app.services.tmdb import TMDBService, TMDBUnavailable


async def main() -> None:
    db = SessionLocal()
    try:
        service = TMDBService(db)
        if not service.enabled:
            raise SystemExit("TMDB_API_KEY is missing from .env")

        interactions = list(
            db.scalars(
                select(UserMovieInteraction).options(selectinload(UserMovieInteraction.movie))
            ).unique().all()
        )
        interactions = [i for i in interactions if i.movie and i.movie.metadata_updated_at is None]
        interactions.sort(
            key=lambda i: (
                i.rating is not None,
                float(i.rating or 0),
                bool(i.watched),
                bool(i.watchlist),
                int(i.rewatch_count or 0),
            ),
            reverse=True,
        )

        movies: list[Movie] = []
        seen: set[int] = set()
        for interaction in interactions:
            if interaction.movie_id in seen:
                continue
            seen.add(interaction.movie_id)
            # Reset prior low-confidence misses so an upgraded matcher can retry them.
            interaction.movie.match_confidence = None
            movies.append(interaction.movie)
        db.commit()

        total = len(movies)
        if total == 0:
            print("✅ No missing TMDB metadata. Everything already enriched.")
            return

        print(f"Found {total} movies still missing TMDB metadata.")
        print("This is resumable: every attempt is committed immediately.\n")
        matched = 0
        unmatched: list[str] = []
        failed: list[str] = []

        for index, movie in enumerate(movies, 1):
            label = f"{movie.title} ({movie.year or '?'})"
            try:
                result = await service.enrich_movie(movie)
                if result:
                    matched += 1
                    status = "matched"
                else:
                    unmatched.append(label)
                    status = "no confident match"
                db.commit()
            except TMDBUnavailable as exc:
                db.rollback()
                failed.append(f"{label}: {exc}")
                status = "TMDB temporarily unavailable"
                await asyncio.sleep(2.0)
            except Exception as exc:
                db.rollback()
                failed.append(f"{label}: {type(exc).__name__}: {exc}")
                status = "error"
            print(f"[{index}/{total}] {status}: {label}")

        out = Path("tmdb_unmatched.txt")
        out.write_text("\n".join(["Movies with no confident TMDB match:", *unmatched, "", "Errors:", *failed]), encoding="utf-8")
        print("\n========================================")
        print("TMDB BACKFILL COMPLETE")
        print("========================================")
        print(f"Matched:   {matched}")
        print(f"Unmatched: {len(unmatched)}")
        print(f"Errors:    {len(failed)}")
        print(f"Report:    {out.resolve()}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
